"""Job de Billing — Disparos automáticos de cobrança.

Busca cobranças PENDING/OVERDUE no Supabase (sincronizado do Asaas),
aplica régua de dias úteis, e envia cobrança via WhatsApp.

Salva contexto no histórico ANTES de enviar (se envio falhar, contexto já está).

Uso:
    python jobs/billing_job.py            # Roda manualmente
    PM2 cron: seg-sex às 9h (ecosystem.config.js)
"""

import asyncio
import sys
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from infra.supabase import get_supabase
from core.constants import TABLE_LEADS, TABLE_ASAAS_CLIENTES, TABLE_ASAAS_COBRANCAS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Régua de cobrança: offsets em dias úteis onde envia
SCHEDULE = [0, 1, 3, 5, 7, 10, 15]

# Templates aprovados — texto EXATO do WhatsApp, sem emoji, sem alteração
TEMPLATES = {
    "due_date": (
        "Olá, {nome}. Sua mensalidade de R$ {valor} vence hoje ({vencimento}).\n\n"
        "Link para pagamento: {link}\n\n"
        "Se já efetuou o pagamento, desconsidere esta mensagem."
    ),
    "overdue": (
        "Olá, {nome}. Sua mensalidade de R$ {valor} com vencimento em {vencimento} encontra-se em aberto.\n\n"
        "Para regularizar, acesse: {link}\n\n"
        "Se já efetuou o pagamento, desconsidere esta mensagem.\n"
        "Em caso de dúvida, responda aqui."
    ),
}


def count_business_days(from_date: date, to_date: date) -> int:
    """Conta dias úteis entre duas datas (sem feriados)."""
    if from_date == to_date:
        return 0
    sign = 1 if to_date > from_date else -1
    start = min(from_date, to_date)
    end = max(from_date, to_date)
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:  # seg-sex
            count += 1
        current += timedelta(days=1)
    return count * sign


def get_template(offset: int) -> tuple:
    """Retorna (template_key, template) baseado no offset."""
    if offset == 0:
        return "due_date", TEMPLATES["due_date"]
    return "overdue", TEMPLATES["overdue"]


def buscar_elegiveis(hoje: date) -> list:
    """Busca cobranças elegíveis para disparo hoje."""
    supabase = get_supabase()
    if not supabase:
        return []

    # Janela: D-2 a D+15 a partir de hoje
    min_date = (hoje - timedelta(days=20)).isoformat()  # margem para dias úteis
    max_date = (hoje + timedelta(days=5)).isoformat()

    try:
        # Cobranças PENDING (vencimento próximo)
        pending = supabase.table(TABLE_ASAAS_COBRANCAS).select(
            "id, customer_id, value, due_date, status, invoice_url"
        ).in_(
            "status", ["PENDING", "OVERDUE"]
        ).is_(
            "deleted_at", "null"
        ).gte("due_date", min_date).lte("due_date", max_date).execute()

        if not pending.data:
            return []

        # Buscar clientes para cada cobrança
        customer_ids = list({c["customer_id"] for c in pending.data})
        clientes = supabase.table(TABLE_ASAAS_CLIENTES).select(
            "id, name, mobile_phone, cpf_cnpj"
        ).in_("id", customer_ids).is_("deleted_at", "null").execute()

        cliente_map = {c["id"]: c for c in (clientes.data or [])}

        elegiveis = []
        for cob in pending.data:
            cliente = cliente_map.get(cob["customer_id"])
            if not cliente:
                continue

            phone = cliente.get("mobile_phone", "")
            if not phone or len(phone) < 10:
                continue

            due = date.fromisoformat(cob["due_date"][:10])
            offset = count_business_days(due, hoje)

            if offset not in SCHEDULE:
                continue

            template_key, template = get_template(offset)

            link = cob.get("invoice_url") or ""
            if not link:
                logger.warning(f"[BILLING] Cobrança {cob['id']} sem link de pagamento, pulando")
                continue
            message = template.format(
                nome=cliente.get("name", "Cliente"),
                valor=f"{cob['value']:.2f}",
                vencimento=due.strftime("%d/%m/%Y"),
                link=link,
            )

            elegiveis.append({
                "phone": phone,
                "message": message,
                "reference_id": cob["id"],
                "context_type": "billing",
                "template_key": template_key,
                "offset": offset,
            })

        return elegiveis

    except Exception as e:
        logger.exception("[BILLING] Falha ao buscar elegíveis")
        return []


async def run_billing():
    """Entry point do billing job."""
    from infra.redis import get_redis_service

    hoje = date.today()
    weekday = hoje.weekday()
    if weekday >= 5:  # sáb/dom
        logger.info("[BILLING] Fim de semana, pulando")
        return

    redis = await get_redis_service()

    # Lock Redis
    lock_key = "lock:billing_job"
    if not await redis.client.set(lock_key, "1", nx=True, ex=3600):
        logger.info("[BILLING] Já em execução")
        return

    try:
        logger.info("[BILLING] Iniciando")
        elegiveis = buscar_elegiveis(hoje)
        logger.info(f"[BILLING] {len(elegiveis)} elegíveis")

        enviados = 0
        erros = 0

        for item in elegiveis:
            try:
                ok = await _processar_disparo(item, redis)
                if ok:
                    enviados += 1
            except Exception as e:
                erros += 1
                logger.error(f"[BILLING] Erro: {e}", exc_info=True)
                from infra.incidentes import registrar_incidente
                registrar_incidente(item.get("phone", "?"), "billing_erro", str(e)[:300])

        logger.info(f"[BILLING] Concluído: enviados={enviados} erros={erros}")

    finally:
        await redis.client.delete(lock_key)


async def _processar_disparo(item: dict, redis) -> bool:
    """Processa um disparo: anti-duplicata -> salvar contexto -> enviar."""
    from infra.event_logger import log_event

    phone = item["phone"]
    message = item["message"]
    reference_id = item["reference_id"]
    context_type = item["context_type"]
    clean_phone = "".join(filter(str.isdigit, phone))

    # Verificar pausa
    if await redis.is_paused(phone):
        logger.info(f"[BILLING:{phone}] Pausado, adiando")
        log_event("billing_skipped", phone, reason="paused")
        return False

    # Verificar snooze (lead prometeu pagar em data X)
    if await redis.is_snoozed(phone, "billing"):
        snooze_until = await redis.snooze_get(phone, "billing")
        logger.info(f"[BILLING:{phone}] Snooze ativo até {snooze_until}, pulando")
        log_event("billing_skipped", phone, reason="snoozed", until=snooze_until)
        return False

    # Fallback: checar snooze no Supabase (caso Redis reiniciou)
    try:
        _sb = get_supabase()
        if _sb:
            _lead_snooze = _sb.table(TABLE_LEADS).select(
                "billing_snooze_until"
            ).eq("telefone", clean_phone).limit(1).execute()
            if _lead_snooze.data:
                snooze_db = _lead_snooze.data[0].get("billing_snooze_until")
                if snooze_db:
                    if date.fromisoformat(snooze_db) >= date.today():
                        logger.info(f"[BILLING:{phone}] Snooze DB até {snooze_db}, pulando")
                        # Restaurar no Redis
                        await redis.snooze_set(phone, snooze_db)
                        return False
                    else:
                        # Snooze expirou — limpar
                        _sb.table(TABLE_LEADS).update(
                            {"billing_snooze_until": None}
                        ).eq("telefone", clean_phone).execute()
    except Exception as e:
        logger.warning(f"[BILLING:{phone}] Snooze DB check falhou: {e}")

    # Anti-duplicata
    dedup_key = f"dispatch:{phone}:{context_type}:{reference_id}:{date.today().isoformat()}"
    if await redis.client.exists(dedup_key):
        logger.info(f"[BILLING:{phone}] Já enviou hoje")
        return False

    # ORDEM CRÍTICA: salvar contexto ANTES de enviar
    supabase = get_supabase()
    if not supabase:
        return False

    now = datetime.now(timezone.utc).isoformat()

    # Buscar lead
    lead = None
    for tel in [clean_phone, clean_phone[2:] if clean_phone.startswith("55") else f"55{clean_phone}"]:
        result = supabase.table(TABLE_LEADS).select(
            "id, conversation_history"
        ).eq("telefone", tel).limit(1).execute()
        if result.data:
            lead = result.data[0]
            break

    if not lead:
        # Criar lead se não existe
        from infra.nodes_supabase import upsert_lead
        lead_id = upsert_lead(clean_phone)
        if lead_id:
            result = supabase.table(TABLE_LEADS).select(
                "id, conversation_history"
            ).eq("id", lead_id).limit(1).execute()
            if result.data:
                lead = result.data[0]

    if not lead:
        logger.warning(f"[BILLING:{phone}] Lead não encontrado/criado")
        return False

    # Salvar contexto no histórico
    history = lead.get("conversation_history") or {"messages": []}
    history["messages"].append({
        "role": "model",
        "content": message,
        "timestamp": now,
        "context": context_type,
        "reference_id": reference_id,
    })

    supabase.table(TABLE_LEADS).update({
        "conversation_history": history,
        "updated_at": now,
    }).eq("id", lead["id"]).execute()

    # Enviar via Leadbox
    from infra.leadbox_client import enviar_resposta_leadbox

    tel_envio = clean_phone if clean_phone.startswith("55") else f"55{clean_phone}"

    if not enviar_resposta_leadbox(tel_envio, message, raw=True):
        logger.error(f"[BILLING:{phone}] Leadbox erro ao enviar")
        log_event("billing_error", phone, reason="leadbox_send_failed", template=item.get("template_key"))
        # Contexto já salvo, lead vai ter contexto quando responder
        await redis.client.set(dedup_key, "1", ex=86400)
        return False

    # Mover ticket para fila de cobranças (544, IA user 1095)
    from infra.leadbox_client import mover_para_fila
    from core.constants import QUEUE_BILLING
    mover_para_fila(tel_envio, queue_id=QUEUE_BILLING, user_id=1095)

    # Marcar anti-duplicata (24h)
    await redis.client.set(dedup_key, "1", ex=86400)
    logger.info(f"[BILLING:{phone}] Enviado ({item['template_key']}, offset={item['offset']})")
    log_event("billing_sent", phone, template=item.get("template_key"), offset=item.get("offset"), ref=reference_id)
    return True


if __name__ == "__main__":
    asyncio.run(run_billing())
