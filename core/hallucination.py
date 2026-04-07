"""
Detecção de hallucination do agente.

Verifica se a Ana afirmou ter executado uma tool (ex: "transferi", "registrei")
sem realmente tê-la chamado. Retorna lista de tools com hallucination detectada.
"""

import logging
import re

logger = logging.getLogger(__name__)

_HALL_CHECKS = [
    ("transferir_departamento", [r"\btransferi\b", r"\bencaminhei\b", r"\bdirecionei\b", "te passo para"]),
    ("registrar_compromisso", [r"\bregistrei\b", r"\banotei o compromisso\b", "compromisso registrado"]),
    ("consultar_cliente", [r"\bverifiquei\b", r"\bconsultei\b", "encontrei no sistema", r"\blocalizei\b"]),
]


def detectar_hallucination(novas_mensagens: list, phone: str) -> list[str]:
    """
    Detecta tools que Ana disse ter chamado mas não chamou.

    Args:
        novas_mensagens: Mensagens novas do resultado do graph (AIMessage + ToolMessage)
        phone: Telefone do lead (para logging)

    Returns:
        Lista de nomes de tools com hallucination detectada (vazia se nenhuma)
    """
    from langchain_core.messages import AIMessage

    # Extrair resposta final (último AIMessage com conteúdo)
    resposta = None
    for msg in reversed(novas_mensagens):
        if isinstance(msg, AIMessage) and msg.content:
            content = msg.content
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
            if content.strip():
                resposta = content.strip()
                break

    if not resposta:
        return []

    tools_chamadas = {
        tc["name"]
        for m in novas_mensagens
        if isinstance(m, AIMessage) and m.tool_calls
        for tc in m.tool_calls
    }

    resp_lower = resposta.lower()
    hallucinations = []

    for tool_name, frases in _HALL_CHECKS:
        if tool_name not in tools_chamadas and any(re.search(f, resp_lower) for f in frases):
            hallucinations.append(tool_name)

    return hallucinations
