---
name: lead-simulator
description: "Simula conversas reais de clientes com a Ana (agente da Aluga-Ar) para testar cenários de cobrança, manutenção e atendimento. Use quando quiser testar o comportamento da IA, validar tool calls, verificar se a Ana responde corretamente em contexto de disparo (billing/manutenção), ou rodar uma suite de cenários end-to-end — mesmo sem WhatsApp real. Também use quando o usuário pedir para 'simular', 'testar cenário', 'rodar simulação', ou 'validar resposta da Ana'."
---

# Lead Simulator — Teste End-to-End da Ana (Aluga-Ar)

Simula conversas reais de clientes com a agente Ana, chamando o Gemini real com mocks de infraestrutura (Supabase, UAZAPI, Redis). Valida tool calls, argumentos e respostas.

## Quando usar

- "simule cenário B1" → roda cenário pré-definido
- "simule todos os cenários de billing" → roda grupo
- "simule: cliente pergunta segunda via do boleto" → cenário ad-hoc
- "rode a suite completa" → todos os cenários + relatório

## Como funciona

O script `simulate.py` faz:

1. Monta lead mockado (nome, telefone)
2. Injeta histórico com contexto de disparo quando aplicável (billing/manutenção)
3. Invoca `graph.ainvoke()` real (Gemini real, tools reais sobre mocks)
4. Captura: resposta final, tool calls (nome + args), tool results
5. Valida contra expectativas do cenário
6. Gera relatório pass/fail

## Cenários pré-definidos

Consulte `references/scenarios.md` para o catálogo completo com IDs, mensagens, tools esperadas e validações.

### Grupos (9 grupos, 68 cenários)

| Grupo | IDs | Qtd | Testa |
|-------|-----|-----|-------|
| billing | B1-B21 | 21 | Cobrança: disparo, Pix/link, pagou, negociar, contestar, cancelar |
| manutencao | M1-M13 | 13 | Manutenção: disparo, agenda dia/hora, reagenda, defeito urgente, transfere |
| snooze | S1-S8 | 8 | Compromisso de pagamento: registrar_compromisso, snooze billing |
| regressao | R1-R8 | 8 | Bugs reais de produção: ar pingando, CPF salvo, saudação indevida |
| vendas | V1-V6 | 6 | Lead interessado: preço, BTU, contrato, cobertura, multa |
| basico | X1-X4 | 4 | Saudação, fora de escopo, pede CPF, transferência |
| contexto | C1-C3 | 3 | Detecção de contexto: Ana NÃO sauda do zero quando há histórico de disparo |
| edge | E1-E3 | 3 | Casos extremos: mensagem confusa, CPF+aluguel, higienização |
| multimodal | MM1-MM2 | 2 | Comprovante texto, áudio genérico |

### Erros críticos que os cenários detectam

| Erro | Cenários | Como detecta |
|------|----------|--------------|
| Ana sauda do zero ignorando contexto do disparo | C1, C2, C3, M1 | `expect_not_contains: ["Olá! Aqui é a Ana", "Como posso ajudar"]` |
| Ana retorna placeholder em vez de link real | B2, B3 | `expect_not_contains: ["LINK DO HISTORICO", "{link}", "link_placeholder"]` |
| Ana pede CPF quando lead veio de disparo | B1, B4, M1, S1 | `expect_not_contains: ["CPF", "cpf"]` |
| Ana não chama `consultar_cliente` quando deve | B4, B8, B10 | `expect_tools: ["consultar_cliente"]` |
| Ana chama tool errada | M2, R6 | `expect_tools: ["transferir_departamento"]` |
| Ana não registra compromisso de pagamento | S1, S2, S3, S4 | `expect_tools: ["registrar_compromisso"]` |

## Como rodar

### Cenário único

```bash
cd /var/www/ana-langgraph
PYTHONPATH=. .venv/bin/python3 .claude/skills/lead-simulator/scripts/simulate.py B1
```

### Grupo de cenários

```bash
PYTHONPATH=. .venv/bin/python3 .claude/skills/lead-simulator/scripts/simulate.py --group billing
```

### Todos os cenários

```bash
PYTHONPATH=. .venv/bin/python3 .claude/skills/lead-simulator/scripts/simulate.py --all
```

### Cenário ad-hoc

```bash
PYTHONPATH=. .venv/bin/python3 .claude/skills/lead-simulator/scripts/simulate.py \
  --adhoc "Quero pagar meu boleto" \
  --expect-tool consultar_cliente \
  --expect-contains "CPF"
```

### Com relatório JSON

```bash
PYTHONPATH=. .venv/bin/python3 .claude/skills/lead-simulator/scripts/simulate.py --all --report
```

O `--report` gera um arquivo JSON em `.claude/skills/lead-simulator/results/` com timestamp.

## Instruções para Claude Code

Quando o usuário pedir para simular:

1. **Cenário pré-definido**: Identifique o ID e rode `simulate.py <ID>`
2. **Grupo**: Rode `simulate.py --group <nome>`
3. **Suite completa**: Rode `simulate.py --all`
4. **Ad-hoc**: Monte o comando com `--adhoc "<mensagem>"` e flags de expectativa
5. **Sempre** mostre ao usuário: resultado pass/fail, resposta da Ana, tool calls feitos

### Cenário ad-hoc com contexto de disparo

Para testar como se o lead tivesse recebido um disparo:

```bash
PYTHONPATH=. .venv/bin/python3 .claude/skills/lead-simulator/scripts/simulate.py \
  --adhoc "pode ser segunda de manhã" \
  --context manutencao \
  --expect-not-contains "Olá! Aqui é a Ana"
```

### Flags de expectativa para ad-hoc

- `--expect-tool <nome>`: Espera que tool seja chamada
- `--expect-no-tool`: Espera nenhuma tool
- `--expect-contains "<texto>"`: Resposta deve conter texto
- `--expect-not-contains "<texto>"`: Resposta NÃO deve conter texto
- `--context billing|manutencao`: Injeta histórico de disparo antes da mensagem

### Interpretando resultados

Cada cenário mostra:
```
[B1] Billing — lead responde disparo com dúvida
  Mensagem: "Quanto tá minha fatura?"
  Histórico: billing (ref=pay_abc123, link=https://sandbox.asaas.com/i/abc)
  Tool calls: consultar_cliente(phone="5566999881234")
  Resposta: "Verifiquei aqui e você tem 1 cobrança pendente..."
  Validações:
    ✅ Tool consultar_cliente chamada
    ✅ Resposta NÃO contém 'CPF'
    ✅ Resposta NÃO contém 'Olá! Aqui é a Ana'
  Resultado: PASS
```

## Dados mockados

### Lead padrão
```python
LEAD = {"nome": "Carlos Souza", "telefone": "5566999881234"}
```

### Histórico de disparo billing (injetado em cenários B*)
```python
BILLING_HISTORY = {
    "messages": [
        {
            "role": "model",
            "content": "Olá, Carlos! Passando para lembrar que sua mensalidade de R$ 189,90 vence em 03/04/2026.\n\nSegue o link para pagamento:\nhttps://sandbox.asaas.com/i/abc123\n\nQualquer dúvida, estou por aqui!",
            "timestamp": "<now - 2h>",
            "context": "billing",
            "reference_id": "pay_abc123",
        }
    ]
}
```

### Histórico de disparo manutenção (injetado em cenários M*)
```python
MANUTENCAO_HISTORY = {
    "messages": [
        {
            "role": "model",
            "content": "Olá, Carlos! Está chegando a hora da manutenção preventiva do seu ar-condicionado!\n\n*Equipamento:* Springer 12000 BTUs\n*Endereço:* Rua das Flores, 123\n\nA manutenção é gratuita e está inclusa no seu contrato.\n\nQuer agendar? Me fala um dia e horário de preferência!",
            "timestamp": "<now - 2h>",
            "context": "manutencao_preventiva",
            "contract_id": "contract_xyz",
        }
    ]
}
```

### Mock do Supabase (consultar_cliente)
```python
MOCK_CUSTOMER = {
    "id": "cus_mock123",
    "name": "Carlos Souza",
    "cpf_cnpj": "12345678901",
    "mobile_phone": "66999881234",
}
MOCK_COBRANCAS = [{
    "id": "pay_abc123",
    "value": 189.90,
    "due_date": "2026-04-03",
    "status": "PENDING",
    "invoice_url": "https://sandbox.asaas.com/i/abc123",
}]
```

## Arquitetura

```
.claude/skills/lead-simulator/
├── SKILL.md              # Este arquivo
├── scripts/
│   └── simulate.py       # Engine principal
└── references/
    └── scenarios.md      # Catálogo detalhado de cenários
```

### Dependências

- Usa `core/grafo.py` → `graph` (grafo compilado real)
- Usa `core/prompts.py` → `SYSTEM_PROMPT`
- Usa `core/context_detector.py` → `detect_context`, `build_context_prompt`
- Usa `GOOGLE_API_KEY` do `.env` (Gemini real)
- Mock do Supabase (consultar_cliente, buscar_historico, context_detector)
- Mock do Redis (is_paused, _context_extra)
- Mock do Leadbox (transferir_departamento)

### O que NÃO faz

- Não toca em produção (mocks em todo I/O)
- Não envia WhatsApp real
- Não cria dados no Supabase
- Não avalia subjetividade — foca em tool calls e valores objetivos

### Diferenças da skill da Clara (agente-langgraph)

| Aspecto | Clara | Ana |
|---------|-------|-----|
| Tools | 4 (horários, agendar, orçamento, transferir) | 3 (consultar_cliente, transferir, registrar_compromisso) |
| Foco | Agendamento médico + orçamento exames | Cobrança Asaas + manutenção preventiva |
| Contexto de disparo | Não tem | billing e manutencao (context_detector.py) |
| Mocks extras | GCal, cache exames | asaas_clientes, asaas_cobrancas, asaas_contratos |
| Erro crítico #1 | Preço errado | Ana sauda do zero ignorando disparo |
| Erro crítico #2 | Data errada | Placeholder no link de pagamento |
