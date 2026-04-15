# CLAUDE.md — Clone Ana (Conferência de Código)

## Propósito

Este repositório é um **clone do projeto Ana LangGraph** (produção em `/var/www/ana-langgraph`).

O objetivo é ter um ambiente seguro para **visualizar, revisar e editar código sem risco** para produção. Aqui eu faço conferência arquivo por arquivo, marcando seções como **validado** ou **não validado** conforme vou revisando.

## Como funciona a conferência

Cada arquivo passa por revisão manual com o Claude. As seções do código recebem comentários indicando o status:

- `(validado)` — seção revisada e aprovada
- `(não validado)` — seção ainda pendente de revisão

Exemplo (ver `jobs/manutencao_job.py`):
```python
# Cliente Supabase singleton — linha 68 até 90 (validado)
# Mensagem que o cliente recebe no WhatsApp — linha 58 até 66 (não validado)
```

O trabalho é incremental: vou pedindo ao Claude para revisar seções específicas, e conforme aprovo, o selo muda de "não validado" para "validado".

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
