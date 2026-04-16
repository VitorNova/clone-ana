# CLAUDE.md — Clone Ana (Conferência de Código)

## Propósito

Este repositório é um **clone do projeto Ana LangGraph** (produção em `/var/www/ana-langgraph`).

O objetivo é ter um ambiente seguro para **visualizar, revisar e editar código sem risco** para produção. Aqui eu faço conferência arquivo por arquivo, marcando seções como **validado** ou **não validado** conforme vou revisando.

## Como funciona a conferência

Cada arquivo passa por revisão feita por um humano que usa o Claude Code como ferramenta. O código é dividido em seções lógicas, e cada seção recebe um **título-comentário** logo acima do bloco, com o formato:

```
# {Descrição da seção} — linha {início} até {fim} ({selo})
```

### Formato do título

| Parte | Obrigatório | Exemplo |
|-------|-------------|---------|
| Descrição | Sim | `Cliente Supabase singleton` |
| Origem (se veio de outro arquivo) | Não | `(antes em infra/supabase.py)` |
| Linhas | Sim | `linha 68 até 90` |
| Selo | Sim | `(validado)`, `(não validado)`, ou `(boilerplate, não requer validação)` |

### Selos possíveis

- `(validado)` — seção revisada e aprovada
- `(não validado)` — seção pendente de revisão
- `(boilerplate, não requer validação)` — imports, logging setup, `if __name__` — pular
- Selo misto quando parte foi validada e parte não: `(query, filtro status: validados | montagem mensagem: não validado)`

### Exemplos reais (ver `jobs/manutencao_job.py`)

```python
# Importa as bibliotecas necessárias — linha 16 até 33 (boilerplate, não requer validação)
# Constantes centralizadas (antes em core/constants.py) — linha 42 até 56 (não validado)
# Cliente Supabase singleton (antes em infra/supabase.py) — linha 68 até 90 (validado)
# Busca contratos com manutenção em 7 dias — linha 293 até 365 (query, filtro status, fallback telefone: validados | montagem mensagem: não validado)
```

### Regras ao preparar um arquivo para conferência

1. **Ler o arquivo inteiro** e dividir em seções lógicas (uma função, um bloco de constantes, um setup, etc.)
2. **Colocar um título-comentário** acima de cada seção, com descrição, linhas e selo `(não validado)`
3. **Marcar boilerplate** (imports, logging, `if __name__`) com `(boilerplate, não requer validação)`
4. **Se a seção veio de outro arquivo** (ex: job consolidado), incluir a origem: `(antes em infra/supabase.py)`
5. **Nunca alterar o código** ao adicionar títulos — só inserir os comentários
6. O trabalho de revisão é incremental: conforme eu aprovo, o selo muda para `(validado)`

## Arquivo em conferência atual

- `jobs/manutencao_job.py` — em andamento (maioria validada, algumas seções pendentes)

## Projeto original

O projeto original é o agente Ana (Aluga-Ar) — um chatbot WhatsApp que roda em LangGraph + Gemini para a empresa Aluga-Ar. Detalhes completos da arquitetura, stack e regras de negócio estão no CLAUDE.md do repositório de produção.

## Regras para o Claude neste repo

1. **Nunca fazer deploy** — este repo é só para leitura e conferência
2. **Manter os selos** `(validado)` / `(não validado)` nos comentários de seção
3. **Quando eu pedir para revisar uma seção**, analisar a lógica e reportar problemas encontrados
4. **Quando eu aprovar**, mudar o selo para `(validado)`
5. **Não alterar lógica** sem eu pedir — o objetivo é conferir, não refatorar
6. **Respostas curtas** — usar o mínimo de caracteres possível
