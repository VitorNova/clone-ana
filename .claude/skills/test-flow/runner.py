#!/usr/bin/env python3
"""
test-flow runner — testa o grafo LangGraph real da Ana e salva resultado em arquivo único do dia.

Uso:
    cd /var/www/ana-langgraph
    PYTHONPATH=. .venv/bin/python .claude/skills/test-flow/runner.py \
        --name "consulta_fatura" \
        --input "Meu CPF é 12345678901, quero ver minha fatura" \
        --expect-tool "consultar_cliente" \
        --expect "R$|189"

Salva em: .claude/skills/test-flow/flows/YYYY-MM-DD.json (1 arquivo por dia, N flows dentro)
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

# Adicionar raiz do projeto ao path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from langchain_core.messages import AIMessage, HumanMessage

FLOWS_DIR = Path(__file__).parent / "flows"


# ─── Dados de disparo (billing/manutenção) ───────────────────────────────────

BILLING_LINK = "https://sandbox.asaas.com/i/abc123"
TWO_HOURS_AGO = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

DISPATCH_HISTORY = {
    "billing": [{
        "role": "model",
        "content": (
            f"Olá! Passando para lembrar que sua mensalidade de "
            f"R$ 189,90 vence em 03/04/2026.\n\n"
            f"Segue o link para pagamento:\n{BILLING_LINK}\n\n"
            f"Qualquer dúvida, estou por aqui!"
        ),
    }],
    "manutencao": [{
        "role": "model",
        "content": (
            "Olá! Está chegando a hora da manutenção preventiva "
            "do seu ar-condicionado!\n\n"
            "*Equipamento:* Springer 12000 BTUs\n"
            "*Endereço:* Rua das Flores, 123\n\n"
            "A manutenção é gratuita e está inclusa no seu contrato.\n\n"
            "Quer agendar? Me fala um dia e horário de preferência!"
        ),
    }],
}


# ─── Supabase/Leadbox mocks (reutiliza do lead-simulator) ────────────────────

# Inline mock simples — evita dependência circular com o simulate.py
MOCK_CUSTOMER = {
    "id": "cus_mock123",
    "name": "Carlos Souza",
    "cpf_cnpj": "12345678901",
    "mobile_phone": "66999881234",
    "email": "carlos@email.com",
}

MOCK_COBRANCAS = [{
    "id": "pay_abc123",
    "value": 189.90,
    "due_date": "2026-04-03",
    "status": "PENDING",
    "invoice_url": BILLING_LINK,
    "customer_id": "cus_mock123",
}]

MOCK_CONTRATOS = [{
    "description": "Aluguel Split 12000 BTUs - Rua das Flores 123",
    "value": 189.90,
    "cycle": "MONTHLY",
    "next_due_date": "2026-05-01",
    "qtd_ars": 1,
    "customer_id": "cus_mock123",
    "status": "ACTIVE",
}]


class _MockChain:
    def __init__(self, data=None):
        self._data = data or []

    def select(self, *a, **kw): return self
    def eq(self, col, val):
        if col == "cpf_cnpj":
            return _MockChain([d for d in self._data if d.get("cpf_cnpj") == val])
        if col == "customer_id":
            return _MockChain([d for d in self._data if d.get("customer_id") == val])
        return self
    def ilike(self, col, pattern):
        s = pattern.strip("%")
        if col == "mobile_phone":
            return _MockChain([d for d in self._data if s in d.get("mobile_phone", "")])
        return self
    def in_(self, col, vals):
        if col == "status":
            return _MockChain([d for d in self._data if d.get("status") in vals])
        return self
    def is_(self, *a, **kw): return self
    def gte(self, *a, **kw): return self
    def order(self, *a, **kw): return self
    def limit(self, n):
        self._data = self._data[:n]
        return self
    def execute(self):
        return MagicMock(data=self._data)


class _MockSupabase:
    def table(self, name):
        if name == "asaas_clientes":
            return _MockChain([MOCK_CUSTOMER])
        if name == "asaas_cobrancas":
            return _MockChain(MOCK_COBRANCAS)
        if name == "asaas_contratos":
            return _MockChain(MOCK_CONTRATOS)
        if name == "ana_leads":
            return _MockChain([])
        return _MockChain([])


def _mock_supabase():
    return patch("core.tools._get_supabase", return_value=_MockSupabase())


def _mock_leadbox():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.post = MagicMock(return_value=mock_resp)
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    return patch("core.tools.httpx.Client", return_value=mock_client)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _format_tools(tools: List[dict]) -> str:
    if not tools:
        return "nenhuma"
    parts = []
    for t in tools:
        args_str = ", ".join(f"{k}={v!r}" for k, v in t["args"].items())
        parts.append(f"{t['name']}({args_str})")
    return "\n".join(parts)


def _build_nodes(result: dict) -> List[dict]:
    tool_str = _format_tools(result["tools"])
    has_tool = bool(result["tools"])
    return [
        {"id": 1, "label": "INPUT", "data": result["input"]},
        {"id": 2, "label": "TOOL", "input": tool_str if has_tool else None,
         "output": result["response"][:300] if has_tool else None},
        {"id": 3, "label": "OUTPUT IA", "data": result["response"]},
        {"id": 4, "label": "VALIDAÇÃO",
         "criterios": [{"criterio": v["criterio"], "status": v["status"]}
                       for v in result["validations"]],
         "status": result["status_clean"]},
        {"id": 5, "label": "RESULTADO",
         "status": result["status_clean"],
         "duracao_ms": result["duration_ms"]},
    ]


# ─── Engine ──────────────────────────────────────────────────────────────────

async def run_flow(
    name: str,
    user_input: str,
    expect: List[str],
    forbidden: List[str],
    expect_tool: Optional[str] = None,
    context: Optional[str] = None,
) -> dict:
    from core.grafo import graph, _context_extra
    from core.context_detector import build_context_prompt

    phone = "5500000000000"

    # Injetar contexto de disparo
    _context_extra.pop(phone, None)
    if context == "billing":
        _context_extra[phone] = build_context_prompt("billing", "pay_abc123")
    elif context == "manutencao":
        _context_extra[phone] = build_context_prompt("manutencao", "contract_xyz")

    # Montar mensagens (SEM SystemMessage — call_model adiciona)
    messages = []

    # Histórico de disparo
    if context and context in DISPATCH_HISTORY:
        for m in DISPATCH_HISTORY[context]:
            messages.append(AIMessage(content=m["content"]))

    # Mensagem do cliente
    messages.append(HumanMessage(content=user_input))

    # Invocar grafo com mocks
    t0 = time.time()
    with _mock_supabase():
        with _mock_leadbox():
            state = await graph.ainvoke(
                {"messages": messages, "phone": phone},
            )
    duration_ms = int((time.time() - t0) * 1000)

    # Limpar contexto
    _context_extra.pop(phone, None)

    # Extrair tool calls e resposta
    tools_called = []
    response_text = ""
    for msg in state["messages"]:
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tools_called.append({"name": tc["name"], "args": tc["args"]})
            if msg.content:
                content = msg.content
                if isinstance(content, list):
                    content = " ".join(
                        p.get("text", "") for p in content if isinstance(p, dict)
                    )
                if content.strip():
                    response_text = content.strip()

    # Validações
    validations = []
    all_pass = True

    for term in expect:
        ok = term.lower() in response_text.lower()
        validations.append({
            "criterio": term, "tipo": "expect",
            "status": "PASS" if ok else "FAIL",
        })
        if not ok:
            all_pass = False

    for term in forbidden:
        ok = term.lower() not in response_text.lower()
        validations.append({
            "criterio": term, "tipo": "forbidden",
            "status": "PASS" if ok else "FAIL",
        })
        if not ok:
            all_pass = False

    if expect_tool:
        tool_names = [t["name"] for t in tools_called]
        ok = expect_tool in tool_names
        validations.append({
            "criterio": f"tool:{expect_tool}", "tipo": "expect_tool",
            "status": "PASS" if ok else "FAIL",
        })
        if not ok:
            all_pass = False

    has_criteria = bool(expect or forbidden or expect_tool)
    status_clean = "PASS" if all_pass else "FAIL" if has_criteria else "SEM_VALIDACAO"

    return {
        "name": name,
        "input": user_input,
        "tools": tools_called,
        "response": response_text,
        "status_clean": status_clean,
        "validations": validations,
        "duration_ms": duration_ms,
        "all_pass": all_pass,
    }


# ─── Persistência ────────────────────────────────────────────────────────────

def save_flow(result: dict) -> tuple:
    """Adiciona flow ao arquivo único do dia. Retorna (filepath, flow_id)."""
    today = datetime.now().strftime("%Y-%m-%d")
    FLOWS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = FLOWS_DIR / f"{today}.json"

    if filepath.exists():
        day_data = json.loads(filepath.read_text(encoding="utf-8"))
    else:
        day_data = {
            "data": today, "proposito": "",
            "total": 0, "pass": 0, "fail": 0, "flows": [],
        }

    existing_nums = [
        int(f["id"].split("_")[1])
        for f in day_data["flows"]
        if f.get("id", "").startswith("flow_")
    ]
    next_num = max(existing_nums, default=0) + 1
    flow_id = f"flow_{next_num:03d}"

    diagnostico = ""
    if not result["all_pass"]:
        falhas = [v for v in result["validations"] if v["status"] == "FAIL"]
        diagnostico = "; ".join(
            f"Termo '{f['criterio']}' "
            f"{'esperado mas AUSENTE' if f['tipo'] in ('expect', 'expect_tool') else 'proibido mas PRESENTE'}"
            for f in falhas
        )

    flow_entry = {
        "id": flow_id,
        "name": result["name"],
        "input": result["input"],
        "status": result["status_clean"],
        "duracao_ms": result["duration_ms"],
        "nodes": _build_nodes(result),
    }
    if diagnostico:
        flow_entry["diagnostico"] = diagnostico

    day_data["flows"].append(flow_entry)
    day_data["total"] = len(day_data["flows"])
    day_data["pass"] = sum(1 for f in day_data["flows"] if f["status"] == "PASS")
    day_data["fail"] = sum(1 for f in day_data["flows"] if f["status"] == "FAIL")

    filepath.write_text(
        json.dumps(day_data, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return filepath, flow_id


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="test-flow runner — Ana")
    parser.add_argument("--name", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--expect", default="")
    parser.add_argument("--forbidden", default="")
    parser.add_argument("--expect-tool", default=None)
    parser.add_argument("--context", default=None,
                        help="Contexto de disparo: billing ou manutencao")
    args = parser.parse_args()

    expect = [t.strip() for t in args.expect.split("|") if t.strip()]
    forbidden = [t.strip() for t in args.forbidden.split("|") if t.strip()]

    print(f"Rodando flow: {args.name}")
    result = asyncio.run(run_flow(
        args.name, args.input, expect, forbidden,
        expect_tool=args.expect_tool, context=args.context,
    ))

    color = "\033[92m" if result["status_clean"] == "PASS" else "\033[91m"
    reset = "\033[0m"
    tools_str = ", ".join(t["name"] for t in result["tools"]) or "nenhuma"

    print(f"  Tool: {tools_str}")
    print(f"  Status: {color}{result['status_clean']}{reset}")
    print(f"  Tempo: {result['duration_ms']}ms")
    print(f"  Output: {result['response'][:200]}")

    if result["validations"]:
        for v in result["validations"]:
            icon = "+" if v["status"] == "PASS" else "X"
            print(f"  [{icon}] {v['tipo']}({v['criterio']})")

    filepath, flow_id = save_flow(result)
    print(f"  Salvo: {filepath} ({flow_id})")

    if result["status_clean"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
