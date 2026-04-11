---
name: test-flow
description: "Testa o agente Ana (LangGraph real) com uma mensagem de cliente, captura tool calls + resposta, valida contra critérios, e salva resultado como flow visual. Use quando quiser testar um cenário individual rapidamente — 'testar flow', 'rodar test-flow', 'validar resposta da Ana'."
---

# test-flow — Teste Individual com Flow Visual

Roda uma mensagem contra o grafo LangGraph real (Gemini + tools), captura tudo, valida, e salva como flow JSON com 5 nós.

## Quando usar

- "teste flow: qual minha fatura?" → roda e salva
- "rode test-flow para manutenção" → cenário ad-hoc
- "valide se consulta retorna cobrança" → com critérios

## Como rodar

```bash
cd /var/www/ana-langgraph

# Sem validação (registra output)
PYTHONPATH=. .venv/bin/python .claude/skills/test-flow/runner.py \
  --name "consulta_fatura" \
  --input "Qual minha próxima fatura?"

# Com validação
PYTHONPATH=. .venv/bin/python .claude/skills/test-flow/runner.py \
  --name "consulta_fatura" \
  --input "Meu CPF é 12345678901, quero ver minha fatura" \
  --expect-tool "consultar_cliente" \
  --expect "R$|189"

# Com contexto de disparo
PYTHONPATH=. .venv/bin/python .claude/skills/test-flow/runner.py \
  --name "billing_link" \
  --input "Manda o pix" \
  --context billing \
  --expect "sandbox.asaas.com" \
  --forbidden "CPF"
```

## Parâmetros

| Flag | Obrigatório | Descrição |
|---|---|---|
| `--name` | sim | Nome do teste (usado no flow) |
| `--input` | sim | Mensagem exata do cliente |
| `--expect` | não | Termos que devem aparecer na resposta (separados por \|) |
| `--forbidden` | não | Termos que NÃO podem aparecer (separados por \|) |
| `--expect-tool` | não | Nome da tool que deve ser chamada |
| `--context` | não | Contexto de disparo: `billing` ou `manutencao` |

## Status possíveis

- **PASS** — todos os critérios passaram
- **FAIL** — ao menos um critério falhou
- **SEM_VALIDACAO** — sem --expect/--forbidden (só registra)

## Onde ficam os flows

```
.claude/skills/test-flow/flows/
└── 2026-03-28.json   ← 1 arquivo por dia, N flows dentro
```

## Formato do flow (5 nós)

1. **INPUT** — mensagem do cliente
2. **TOOL** — tool chamada + args (ou "nenhuma")
3. **OUTPUT IA** — resposta final do agente
4. **VALIDAÇÃO** — tabela de critérios pass/fail
5. **RESULTADO** — status + duração

## Diferença do lead-simulator

| | test-flow | lead-simulator |
|---|---|---|
| Scope | 1 mensagem | Suite de cenários |
| Output | Flow JSON (5 nós) | JSON report |
| Validação | --expect/--forbidden | cenários pré-definidos |
| Uso | teste rápido ad-hoc | regressão completa |

## Tools disponíveis da Ana (3)

- `consultar_cliente` — dados pessoais, cobranças Asaas, contratos
- `transferir_departamento` — transfere para fila humana no Leadbox
- `registrar_compromisso` — registra compromisso de pagamento (data), silencia disparos billing via snooze
