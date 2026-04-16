# MEMORY.md — Clone Ana (Registro de Sessões)

Registro do que foi feito em cada sessão de conferência. Leia antes de qualquer tarefa.

---

## [15/04/2026] Sessão 1 — `jobs/manutencao_job.py`

**Validado:**
- Linha 42–56 — Constantes centralizadas (antes em `core/constants.py`)
  - 4 tabelas conferidas no Supabase via MCP: `ana_leads`, `asaas_clientes`, `contract_details`, `ana_incidentes` — todas existem com colunas corretas
  - Variáveis Leadbox confirmadas com agente de produção (anaproducao): valores reais vêm do `.env`
  - Commit: `e32418a`

**Outros commits:**
- MEMORY.md reescrito — apenas registro de sessões (`d6875ca`)
- CLAUDE.md — conferência é feita por humano usando Claude Code (`1ab3b0a`)

**Pendente:**
- Linha 58–66 — Template WhatsApp `(não validado)`
- Linha 293–365 — Montagem da mensagem `(parcial: montagem mensagem não validado)`
- Linha 367–405 — `run_manutencao()` `(não validado)`
