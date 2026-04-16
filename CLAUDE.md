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

### Como consolidar um braço (job) em arquivo único

Quando o usuário pedir para consolidar um braço para conferência, gerar um arquivo
`jobs/<nome>_job.py` que reúna todo o código necessário num único arquivo.

#### O que inlinar (copiar para dentro do arquivo)

Inlinar **toda função, classe ou constante que o job usa diretamente** de `core/` e `infra/`.
Para cada módulo importado pelo job, percorrer a árvore de dependências e trazer junto.
Copiar apenas o que é usado — não copiar o módulo inteiro se só uma função é chamada.

**Sempre inlinar:**
- Constantes usadas pelo job (de `core/constants.py`)
- Clients singleton (Supabase, Redis) — copiar a função factory e o pattern singleton
- Funções de envio (Leadbox, WhatsApp) — junto com helpers como marker anti-eco
- Event logger e registro de incidentes
- Funções de persistência usadas pelo job (upsert_lead, salvar_mensagem, etc.)
- Context detector, se o job salva/lê contexto no histórico

**Regra geral:** se está em `infra/` ou `core/` e o job chama, inlinar.

#### O que manter como import externo

- **Bibliotecas de terceiros** (`httpx`, `redis`, `supabase`, `dotenv`, etc.) — nunca inlinar
- **Bibliotecas padrão** (`asyncio`, `json`, `logging`, `os`, etc.) — nunca inlinar
- **Módulos do grafo LangGraph** (`core/grafo.py`, `core/tools.py`, `core/prompts.py`) —
  não inlinar. O job de disparo não roda o grafo; se precisar de algo do grafo, usar
  import local dentro da função (ex: `from langchain_core.messages import AIMessage`)
- **Import local** (dentro de função) é permitido para módulos pesados usados apenas em
  um caminho raro (ex: `langchain_core` só no `buscar_historico`)

#### Como marcar a origem de cada seção

Cada bloco inlinado recebe um comentário-título com a origem:

```python
# Descrição da seção (antes em <arquivo_original>) — linha X até Y (não validado)
```

Exemplo:
```python
# Cliente Supabase singleton (antes em infra/supabase.py) — linha 68 até 90 (não validado)
```

Se a seção é código novo (não veio de outro arquivo), omitir `(antes em ...)`:
```python
# Mensagem que o cliente recebe no WhatsApp — linha 58 até 66 (não validado)
```

#### Selos iniciais

- Todo código inlinado começa como `(não validado)` — quem valida é o humano
- Imports e logging config recebem `(boilerplate, não requer validação)`
- `if __name__ == "__main__"` recebe `(boilerplate, não requer validação)`

#### Ordem das seções no arquivo consolidado

1. **Docstring** — o que o job faz, escopo (só disparo, não inclui grafo), como rodar
2. **Imports de bibliotecas** — padrão + terceiros (boilerplate)
3. **Logging setup** (boilerplate)
4. **Constantes** — inlinadas de `core/constants.py`, só as que o job usa
5. **Templates de mensagem** — textos enviados ao cliente
6. **Infraestrutura base** — Supabase client, event logger, registro de incidentes
7. **Infraestrutura de comunicação** — Redis service, Leadbox client
8. **Funções de dados** — upsert_lead, busca de histórico, persistência
9. **Lógica de negócio** — query principal (buscar contratos/cobranças), montagem de mensagem
10. **Orquestração** — função `run_*()` com lock Redis, loop e contadores
11. **Processamento individual** — função `_processar_*()` com pausa, dedupe, contexto, envio
12. **Módulos auxiliares** — context_detector, build_context_prompt (se usados)
13. **`if __name__`** (boilerplate)

#### Regras de qualidade

- **Não alterar lógica** ao consolidar — copiar fielmente, ajustar apenas imports removidos
- **Adaptar singletons** — se o original usa `from infra.supabase import get_supabase`,
  a versão inline precisa declarar `_supabase_client` e a função `get_supabase()` no próprio arquivo
- **Manter docstrings** das funções originais
- **Adicionar ao docstring do arquivo** a lista de módulos inlinados para referência rápida
- **Numerar as linhas nos títulos** após a consolidação final (quando o arquivo estiver completo)

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
7. **Sempre atualizar o MEMORY.md** após cada validação — registrar o que foi validado, o que falta, e em qual arquivo estamos trabalhando. Commitar e pushar.
