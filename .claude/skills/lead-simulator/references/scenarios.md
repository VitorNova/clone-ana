# Catálogo de Cenários — Lead Simulator (Ana / Aluga-Ar)

## Regra de ouro

A Ana tem **3 tools**: `consultar_cliente`, `transferir_departamento` e `registrar_compromisso`.
Não existe tool de agendamento — manutenção é verbal (coleta dia/hora → transfere para humano).

---

## Resumo: 9 grupos, 68 cenários

| Grupo | IDs | Qtd | Foco |
|-------|-----|-----|------|
| billing | B1-B21 | 21 | Cobrança, Pix, link, pagamento, negociação, cancelamento |
| manutencao | M1-M13 | 13 | Manutenção preventiva, agendamento, defeito urgente |
| snooze | S1-S8 | 8 | Compromisso de pagamento, registrar_compromisso |
| regressao | R1-R8 | 8 | Bugs reais de produção |
| vendas | V1-V6 | 6 | Lead interessado em alugar |
| basico | X1-X4 | 4 | Saudação, fora de escopo, CPF, transferência |
| contexto | C1-C3 | 3 | Anti-saudação (não sauda do zero após disparo) |
| edge | E1-E3 | 3 | Casos extremos |
| multimodal | MM1-MM2 | 2 | Comprovante texto, áudio |

---

## Grupo: billing (B1-B21) — Cobrança / Pix

### B1 — Lead responde disparo com dúvida
- **Contexto**: billing (link já enviado no disparo)
- **Mensagem**: "Quanto tá minha fatura?"
- **Tool esperada**: `consultar_cliente` (sem CPF, busca por telefone)
- **Validações**:
  - Tool `consultar_cliente` chamada
  - Resposta NÃO contém "CPF" (contexto billing = já sabemos quem é)
  - Resposta NÃO contém "Aqui é a Ana" (não sauda do zero)

### B2 — Lead pede Pix / link de pagamento
- **Contexto**: billing (link: `https://sandbox.asaas.com/i/abc123`)
- **Mensagem**: "Manda o pix"
- **Tool esperada**: nenhuma (link já está no histórico)
- **Validações**:
  - Resposta contém "sandbox.asaas.com/i/abc123"
  - Resposta NÃO contém "LINK DO HISTORICO" (placeholder)

### B3 — Lead pede boleto SEM contexto (orgânico)
- **Contexto**: nenhum
- **Mensagem**: "Quero meu boleto"
- **Tool esperada**: nenhuma (deve pedir CPF primeiro)
- **Validações**:
  - Resposta contém "CPF" ou "identificar" ou "localizar" ou "cadastro"

### B4 — Lead afirma que pagou (com contexto billing)
- **Contexto**: billing
- **Mensagem**: "Já paguei ontem"
- **Tool esperada**: `consultar_cliente` com `verificar_pagamento=True`
- **Validações**:
  - Tool `consultar_cliente` chamada
  - Resposta NÃO contém "CPF"

### B5 — Lead afirma que pagou SEM contexto → pede CPF
- **Contexto**: nenhum
- **Mensagem**: "Já paguei meu boleto ontem"
- **Validações**:
  - Resposta contém "CPF"

### B6 — Lead quer negociar → financeiro
- **Contexto**: billing
- **Mensagem**: "Tô sem condição de pagar, preciso negociar"
- **Tool esperada**: `transferir_departamento` (queue_id=454)

### B7 — Lead diz 'vou pagar depois' (compromisso vago)
- **Contexto**: billing
- **Mensagem**: "vou pagar depois, essa semana eu resolvo"
- **Tool esperada**: nenhuma (permite consultar_cliente ou registrar_compromisso)
- **Validações**:
  - Resposta NÃO contém "CPF"
  - Resposta contém link, pix, boleto, pagamento, certo, combinado, etc.

### B8 — Lead pede boleto do mês passado (com contexto)
- **Contexto**: billing
- **Mensagem**: "quero o boleto do mês passado, não o desse"
- **Tool esperada**: `consultar_cliente`
- **Validações**:
  - Resposta NÃO contém "CPF"

### B9 — Lead pede Pix SEM contexto de disparo → pede CPF
- **Contexto**: nenhum
- **Mensagem**: "manda o pix pra mim"
- **Validações**:
  - Resposta contém "CPF" ou "identificar" ou "localizar" ou "cadastro"

### B10 — Lead quer saber quanto deve (com contexto)
- **Contexto**: billing
- **Mensagem**: "quanto que eu devo no total?"
- **Tool esperada**: `consultar_cliente`
- **Validações**:
  - Resposta NÃO contém "CPF"

### B11 — Lead recusa pagar → Lázaro
- **Contexto**: billing
- **Mensagem**: "não vou pagar não, tá caro demais isso aí"
- **Tool esperada**: `transferir_departamento` (queue_id=453, user_id=813)

### B12 — Lead envia comprovante por texto (com contexto)
- **Contexto**: billing
- **Mensagem**: "acabei de fazer o pix de R$189,90, segue comprovante"
- **Tool esperada**: `consultar_cliente` com `verificar_pagamento=True`
- **Validações**:
  - Resposta NÃO contém "CPF"

### B13 — Lead insiste que pagou (2a vez) → financeiro
- **Contexto**: billing + histórico de insistência
- **Mensagem**: "já paguei sim, tenho o comprovante aqui"
- **Tool esperada**: `transferir_departamento` (queue_id=454, user_id=814)

### B14 — Lead pede Lázaro pelo nome
- **Contexto**: billing
- **Mensagem**: "quero falar com o Lázaro"
- **Tool esperada**: `transferir_departamento` (queue_id=453, user_id=813)

### B15 — Lead quer cancelar contrato → Nathália
- **Contexto**: billing
- **Mensagem**: "quero cancelar meu contrato, não quero mais"
- **Tool esperada**: `transferir_departamento` (queue_id=453, user_id=815)

### B16 — Lead quer devolver equipamento → Nathália
- **Contexto**: billing
- **Mensagem**: "quero devolver o ar condicionado, vem buscar"
- **Tool esperada**: `transferir_departamento` (queue_id=453)

### B17 — Lead de outra cidade com contexto (já é cliente)
- **Contexto**: billing
- **Mensagem**: "moro em Cuiabá, me manda o boleto"
- **Validações**:
  - Resposta NÃO contém "CPF"

### B18 — Lead responde 'não' seco ao disparo
- **Contexto**: billing
- **Mensagem**: "não"
- **Validações**:
  - Resposta NÃO contém "CPF", "Aqui é a Ana"

### B19 — Lead contesta valor da cobrança → cobranças
- **Contexto**: billing
- **Mensagem**: "esse valor tá errado, não concordo com essa cobrança, quero contestar"
- **Tool esperada**: `transferir_departamento` (queue_id=544)

### B20 — Lead com CPF vinculado pede segunda via (sem dar CPF de novo)
- **Contexto**: billing
- **Mensagem**: "me manda a segunda via do boleto"
- **Validações**:
  - Resposta contém "sandbox.asaas.com"
  - Resposta NÃO contém "CPF"

### B21 — Lead diz que pagou + comprovante + IA não acha → financeiro
- **Contexto**: billing + histórico de insistência com comprovante
- **Mensagem**: "tá aqui o comprovante do pix que fiz ontem, R$189,90"
- **Tool esperada**: `transferir_departamento` (queue_id=454, user_id=814)

---

## Grupo: manutencao (M1-M13) — Manutenção preventiva

### M1 — Lead responde disparo com dia/hora
- **Contexto**: manutencao
- **Mensagem**: "Pode ser segunda de manhã"
- **Validações**:
  - Resposta NÃO contém "CPF", "Aqui é a Ana"

### M2 — Confirma dia/hora → transfere humano
- **Contexto**: manutencao + histórico de agendamento
- **Mensagem**: "Isso, pode transferir"
- **Tool esperada**: `transferir_departamento` (queue_id=453)

### M3 — Lead recusa → transfere Nathália
- **Contexto**: manutencao
- **Mensagem**: "Não preciso de manutenção, tá tudo ok"
- **Tool esperada**: `transferir_departamento` (queue_id=453, user_id=815)

### M4 — Pergunta se manutenção é paga
- **Contexto**: manutencao
- **Mensagem**: "Quanto custa a manutenção?"
- **Validações**:
  - Resposta contém "gratuita" ou "inclusa" ou "grátis" ou "sem custo"

### M5 — Fluxo completo 5 turnos → transfere
- **Contexto**: manutencao + 8 turnos de histórico
- **Mensagem**: "tá bom, pode confirmar com o pessoal"
- **Tool esperada**: `transferir_departamento` (queue_id=453)

### M6 — Lead diz só 'sim' ao disparo → pergunta dia/hora
- **Contexto**: manutencao
- **Mensagem**: "sim"
- **Validações**:
  - Resposta NÃO contém "CPF", "Aqui é a Ana"

### M7 — Lead quer reagendar (muda o dia)
- **Contexto**: manutencao + histórico de agendamento
- **Mensagem**: "não vai dar segunda, pode ser quarta de manhã?"
- **Validações**:
  - Resposta NÃO contém "CPF", "erro"

### M8 — Lead muda assunto para cobrança
- **Contexto**: manutencao
- **Mensagem**: "ah, aproveita e me manda o boleto do mês"
- **Validações**:
  - Resposta NÃO contém "erro"

### M9 — Lead pergunta endereço (já veio no disparo)
- **Contexto**: manutencao
- **Mensagem**: "qual endereço vocês vão fazer a manutenção?"
- **Validações**:
  - Resposta contém "Rua das Flores" ou "Flores" ou "123" ou "endereço"

### M10 — Lead quer cancelar CONTRATO → transfere
- **Contexto**: manutencao
- **Mensagem**: "não quero mais o aluguel, quero cancelar meu contrato"
- **Tool esperada**: `transferir_departamento` (queue_id=453, user_id=815)

### M11 — Lead não vai estar em casa → coleta outro dia
- **Contexto**: manutencao
- **Mensagem**: "não vou estar em casa essa semana toda, só semana que vem"
- **Validações**:
  - Resposta NÃO contém "CPF", "erro"

### M12 — Lead relata defeito urgente (ar parou) → transfere imediato
- **Contexto**: manutencao
- **Mensagem**: "o ar parou de funcionar completamente, não liga mais"
- **Tool esperada**: `transferir_departamento` (queue_id=453, user_id=815)

### M13 — Lead relata defeito SEM contexto (orgânico) → pede CPF
- **Contexto**: nenhum
- **Mensagem**: "tenho um ar alugado com vocês e tá pingando água dentro de casa"
- **Validações**:
  - Resposta contém "CPF" ou "CNPJ" ou "titular"

---

## Grupo: snooze (S1-S8) — Compromisso de pagamento

### S1 — Lead diz 'vou pagar sexta' → registra compromisso
- **Contexto**: billing
- **Mensagem**: "vou pagar sexta-feira sem falta"
- **Tool esperada**: `registrar_compromisso`

### S2 — Lead diz 'pago amanhã' → registra compromisso
- **Contexto**: billing
- **Mensagem**: "pago amanhã de manhã"
- **Tool esperada**: `registrar_compromisso`

### S3 — Lead diz 'vou pagar depois' (vago) → registra compromisso
- **Contexto**: billing
- **Mensagem**: "vou pagar depois, essa semana eu resolvo"
- **Tool esperada**: `registrar_compromisso`

### S4 — Lead diz 'semana que vem' → registra compromisso
- **Contexto**: billing
- **Mensagem**: "só consigo pagar semana que vem, pode ser?"
- **Tool esperada**: `registrar_compromisso`

### S5 — Lead com snooze manda msg pedindo link → Ana responde normal
- **Contexto**: billing + histórico de snooze
- **Mensagem**: "manda o link de novo por favor"
- **Validações**:
  - Resposta contém "sandbox.asaas.com"
  - Resposta NÃO contém "CPF"

### S6 — Lead quer negociar → financeiro (sem snooze)
- **Contexto**: billing
- **Mensagem**: "não tenho como pagar esse valor, preciso negociar parcelas"
- **Tool esperada**: `transferir_departamento` (queue_id=454)

### S7 — Lead SEM contexto diz 'pago sexta' → pede CPF (sem snooze)
- **Contexto**: nenhum
- **Mensagem**: "vou pagar sexta, me manda o boleto"
- **Validações**:
  - Resposta contém "CPF" ou "identificar" ou "localizar" ou "cadastro"

### S8 — Lead responde 'ok' ao disparo → NÃO registra compromisso
- **Contexto**: billing
- **Mensagem**: "ok"
- **Validações**:
  - Nenhuma tool obrigatória (permite consultar_cliente, registrar_compromisso)
  - Resposta NÃO contém "CPF", "erro"

---

## Grupo: regressao (R1-R8) — Bugs reais de produção

### R1 — Ar pingando sem contexto → pede CPF
- **Mensagem**: "minha mãe tem um ar alugado com vocês, está pingando"
- **Validações**:
  - Resposta contém "CPF" ou "CNPJ" ou "titular"

### R2 — Disse vou transferir mas não chamou tool
- **Contexto**: billing
- **Mensagem**: "quero falar com o financeiro"
- **Tool esperada**: `transferir_departamento`
- **Validações**:
  - Resposta NÃO contém "vou te transferir", "vou transferir"

### R3 — CPF salvo com sucesso (deve usar, não confirmar)
- **Mensagem**: "meu cpf é 12345678901"
- **Validações**:
  - Resposta NÃO contém "CPF salvo", "salvo com sucesso"

### R4 — CPF com cobrança (não pode dizer que não encontrou)
- **Mensagem**: "quero pagar minha parcela, meu CPF é 12345678901"
- **Tool esperada**: `consultar_cliente`
- **Validações**:
  - Resposta NÃO contém "não encontrei", "não achei", "não localizei"

### R5 — Ana sauda do zero respondendo disparo billing
- **Contexto**: billing
- **Mensagem**: "oi"
- **Validações**:
  - Resposta NÃO contém "Sou a Ana", "da Aluga Ar", "Como posso ajudar"

### R6 — Manutenção com disparo não pede CPF
- **Contexto**: manutencao
- **Mensagem**: "o ar está fazendo barulho"
- **Tool esperada**: `transferir_departamento`
- **Validações**:
  - Resposta NÃO contém "CPF", "CNPJ"

### R7 — Consulta CPF retorna contrato ativo (status ACTIVE)
- **Mensagem**: "Pará mudança do ar, que ficou de eu mandar as fotos do local. Meu CPF é 12345678901"
- **Tool esperada**: `consultar_cliente`
- **Validações**:
  - Resposta contém "contrato" ou "Split" ou "12000" ou "Flores" ou "189"
  - Resposta NÃO contém "Nenhum contrato"

### R8 — Ar não gela + CPF → transfere atendimento (defeito urgente)
- **Mensagem**: "Não tá gelado direito, meu CPF é 12345678901"
- **Tool esperada**: `transferir_departamento` (queue_id=453, user_id=815)
- **Permite**: `consultar_cliente`

---

## Grupo: vendas (V1-V6) — Lead interessado em alugar

### V1 — Pergunta preço (com ambiente)
- **Mensagem**: "quanto custa o aluguel pra um quarto?"
- **Validações**:
  - Resposta contém "R$" ou "189" ou "mensais" ou "mensal"

### V2 — Qual BTU para quarto 15m²
- **Mensagem**: "não sei qual ar preciso, é pra um quarto de 15m²"
- **Validações**:
  - Resposta contém "12.000" ou "12000" ou "BTU"

### V3 — Como funciona o contrato
- **Mensagem**: "como funciona o aluguel? tem contrato?"
- **Validações**:
  - Resposta contém "12 meses" ou "instalação" ou "manutenção" ou "mensalidade"

### V4 — Fora da área de cobertura
- **Mensagem**: "atende em São Paulo?"
- **Tool esperada**: `transferir_departamento`

### V5 — Quer fechar → coleta nome e CPF
- **Mensagem**: "quero alugar, pode me mandar o contrato"
- **Validações**:
  - Resposta contém "nome" ou "CPF" ou "dados"

### V6 — Multa por cancelamento
- **Mensagem**: "se eu quiser cancelar antes do prazo tem multa?"
- **Validações**:
  - Resposta NÃO contém "CPF", "erro", "não sei"

---

## Grupo: basico (X1-X4) — Cenários gerais

### X1 — Saudação simples
- **Mensagem**: "Oi, tudo bem?"
- **Tool esperada**: nenhuma

### X2 — Fora de escopo
- **Mensagem**: "Vocês vendem ar condicionado?"
- **Tool esperada**: nenhuma

### X3 — Lead pede boleto com CPF
- **Mensagem**: "Quero ver meu boleto, meu CPF é 12345678901"
- **Tool esperada**: `consultar_cliente`

### X4 — Pede humano
- **Mensagem**: "Quero falar com um atendente"
- **Tool esperada**: `transferir_departamento`

---

## Grupo: contexto (C1-C3) — Detecção de contexto (anti-saudação)

### C1 — Resposta genérica a disparo billing
- **Contexto**: billing
- **Mensagem**: "ok"
- **Validações**:
  - Resposta NÃO contém "Aqui é a Ana", "Como posso ajudar"

### C2 — Resposta genérica a disparo manutenção
- **Contexto**: manutencao
- **Mensagem**: "oi"
- **Validações**:
  - Resposta NÃO contém "Aqui é a Ana", "Como posso ajudar"

### C3 — Lead novo sem contexto → saudação OK
- **Mensagem**: "Oi"
- **Tool esperada**: nenhuma

---

## Grupo: edge (E1-E3) — Casos extremos

### E1 — Mensagem confusa/incompleta
- **Mensagem**: "oi sim aquele negócio lá"
- **Tool esperada**: nenhuma

### E2 — Lead quer alugar e já deu CPF → coleta nome
- **Mensagem**: "quero alugar, meu CPF é 12345678901"
- **Validações**:
  - Resposta contém "nome" ou "completo"

### E3 — Pergunta sobre higienização (Mundia Ar)
- **Mensagem**: "vocês fazem higienização de ar?"
- **Validações**:
  - Resposta contém "Mundia" ou "mundia" ou "@mundialar" ou "Instagram"

---

## Grupo: multimodal (MM1-MM2)

### MM1 — Comprovante de pagamento (texto)
- **Contexto**: billing
- **Mensagem**: "acabei de pagar, segue o comprovante do pix de R$189,90"
- **Tool esperada**: `consultar_cliente` com `verificar_pagamento=True`

### MM2 — Áudio genérico
- **Mensagem**: "[mensagem de áudio]"
- **Tool esperada**: nenhuma

---

## Dados mockados

### Lead padrão
```python
LEAD = {"nome": "Carlos Souza", "telefone": "5566999881234"}
```

### Mock consultar_cliente (retorno do Supabase)
```python
MOCK_CUSTOMER = {
    "id": "cus_mock123",
    "name": "Carlos Souza",
    "cpf_cnpj": "12345678901",
    "mobile_phone": "66999881234",
}
MOCK_COBRANCAS_PENDENTES = [{
    "id": "pay_abc123",
    "value": 189.90,
    "due_date": "2026-04-03",
    "status": "PENDING",
    "invoice_url": "https://sandbox.asaas.com/i/abc123",
}]
MOCK_COBRANCAS_PAGAS = [{
    "value": 189.90,
    "due_date": "2026-03-03",
    "payment_date": "2026-03-02",
}]
MOCK_CONTRATOS = [{
    "descricao": "Aluguel Split 12000 BTUs - Rua das Flores 123",
    "valor_mensal": 189.90,
    "data_inicio": "2025-10-01",
    "data_fim": "2026-10-01",
}]
```
