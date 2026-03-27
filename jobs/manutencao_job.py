"""Job de Manutenção Preventiva — Lembrete D-7.

Busca contratos com proxima_manutencao = hoje + 7 dias
e envia lembrete via WhatsApp com dados do equipamento.

Salva contexto "manutencao_preventiva" no histórico para que
o context_detector saiba que o lead está respondendo sobre manutenção.

Uso:
    python jobs/manutencao_job.py           # Roda manualmente
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

TEMPLATE = (
    "Olá, {nome}!\n\n"
    "Está chegando a hora da manutenção preventiva do seu ar-condicionado!\n\n"
    "*Equipamento:* {equipamento}\n"
    "*Endereço:* {endereco}\n\n"
    "A manutenção é gratuita e está inclusa no seu contrato.\n\n"
    "Quer agendar? Me fala um dia e horário de preferência!"
)


def buscar_contratos_d7(hoje: date) -> list:
    """Busca contratos com manutenção prevista para daqui 7 dias."""
    supabase = get_supabase()
    if not supabase:
        return []

    data_alvo = (hoje + timedelta(days=7)).isoformat()

    try:
        result = supabase.table("contract_details").select(
            "id, customer_id, locatario_nome, locatario_telefone, "
            "equipamentos, endereco_instalacao, proxima_manutencao, "
            "maintenance_status"
        ).eq(
            "proxima_manutencao", data_alvo
        ).is_(
            "deleted_at", "null"
        ).execute()

        if not result.data:
            return []

        elegiveis = []
        for contrato in result.data:
            # Pular se já notificado
            if contrato.get("maintenance_status") == "notified":
                continue

            # Buscar telefone: primeiro do contrato, depois do cliente Asaas
            phone = contrato.get("locatario_telefone")
            if not phone:
                customer_id = contrato.get("customer_id")
                if customer_id:
                    cliente = supabase.table("asaas_clientes").select(
                        "mobile_phone"
                    ).eq("id", customer_id).limit(1).execute()
                    if cliente.data:
                        phone = cliente.data[0].get("mobile_phone")

            if not phone or len(phone) < 10:
                logger.warning(f"[MANUTENCAO] Contrato {contrato['id']} sem telefone válido")
                continue

            # Formatar equipamento
            equipamentos = contrato.get("equipamentos") or []
            if equipamentos and isinstance(equipamentos, list):
                eq = equipamentos[0]
                equipamento_str = f"{eq.get('marca', '?')} {eq.get('btus', '?')} BTUs"
                if len(equipamentos) > 1:
                    equipamento_str += f" (+{len(equipamentos)-1} equipamento(s))"
            else:
                equipamento_str = "Ar-condicionado"

            nome = contrato.get("locatario_nome", "Cliente")
            endereco = contrato.get("endereco_instalacao", "Endereço não informado")

            message = TEMPLATE.format(
                nome=nome.split()[0] if nome else "Cliente",  # Primeiro nome
                equipamento=equipamento_str,
                endereco=endereco,
            )

            elegiveis.append({
                "phone": phone,
                "message": message,
                "contract_id": contrato["id"],
                "context_type": "manutencao_preventiva",
            })

        return elegiveis

    except Exception as e:
        logger.exception("[MANUTENCAO] Falha ao buscar contratos")
        return []


async def run_manutencao():
    """Entry point do job de manutenção."""
    from infra.redis import get_redis_service

    hoje = date.today()
    weekday = hoje.weekday()
    if weekday >= 5:
        logger.info("[MANUTENCAO] Fim de semana, pulando")
        return

    redis = await get_redis_service()

    lock_key = "lock:manutencao_job"
    if not await redis.client.set(lock_key, "1", nx=True, ex=3600):
        logger.info("[MANUTENCAO] Já em execução")
        return

    try:
        logger.info("[MANUTENCAO] Iniciando")
        elegiveis = buscar_contratos_d7(hoje)
        logger.info(f"[MANUTENCAO] {len(elegiveis)} contratos para notificar")

        enviados = 0
        erros = 0

        for item in elegiveis:
            try:
                ok = await _processar_notificacao(item, redis)
                if ok:
                    enviados += 1
            except Exception as e:
                erros += 1
                logger.error(f"[MANUTENCAO] Erro: {e}")

        logger.info(f"[MANUTENCAO] Concluído: enviados={enviados} erros={erros}")

    finally:
        await redis.client.delete(lock_key)


async def _processar_notificacao(item: dict, redis) -> bool:
    """Processa uma notificação de manutenção."""
    import os
    import httpx

    phone = item["phone"]
    message = item["message"]
    contract_id = item["contract_id"]
    context_type = item["context_type"]

    if await redis.is_paused(phone):
        logger.info(f"[MANUTENCAO:{phone}] Pausado, adiando")
        return False

    # Anti-duplicata
    dedup_key = f"dispatch:{phone}:{context_type}:{contract_id}:{date.today().isoformat()}"
    if await redis.client.exists(dedup_key):
        logger.info(f"[MANUTENCAO:{phone}] Já notificou hoje")
        return False

    # Salvar contexto ANTES de enviar
    supabase = get_supabase()
    if not supabase:
        return False

    now = datetime.now(timezone.utc).isoformat()
    clean_phone = "".join(filter(str.isdigit, phone))

    # Buscar lead
    lead = None
    for tel in [clean_phone, clean_phone[2:] if clean_phone.startswith("55") else f"55{clean_phone}"]:
        result = supabase.table("ana_leads").select(
            "id, conversation_history"
        ).eq("telefone", tel).limit(1).execute()
        if result.data:
            lead = result.data[0]
            break

    if not lead:
        from infra.persistencia import upsert_lead
        lead_id = upsert_lead(clean_phone)
        if lead_id:
            result = supabase.table("ana_leads").select(
                "id, conversation_history"
            ).eq("id", lead_id).limit(1).execute()
            if result.data:
                lead = result.data[0]

    if not lead:
        logger.warning(f"[MANUTENCAO:{phone}] Lead não encontrado/criado")
        return False

    # Salvar contexto
    history = lead.get("conversation_history") or {"messages": []}
    history["messages"].append({
        "role": "model",
        "content": message,
        "timestamp": now,
        "context": context_type,
        "contract_id": contract_id,
    })

    supabase.table("ana_leads").update({
        "conversation_history": history,
        "updated_at": now,
    }).eq("id", lead["id"]).execute()

    # Marcar contrato como notificado
    try:
        supabase.table("contract_details").update({
            "maintenance_status": "notified",
            "notificacao_enviada_at": now,
        }).eq("id", contract_id).execute()
    except Exception as e:
        logger.warning(f"[MANUTENCAO:{phone}] Erro ao marcar contrato: {e}")

    # Enviar via UAZAPI
    uazapi_url = os.environ.get("UAZAPI_URL", "").rstrip("/")
    uazapi_token = os.environ.get("UAZAPI_TOKEN", "")
    if not uazapi_url or not uazapi_token:
        return False

    tel_envio = clean_phone if clean_phone.startswith("55") else f"55{clean_phone}"

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{uazapi_url}/send/text",
                headers={"token": uazapi_token, "Content-Type": "application/json"},
                json={"number": tel_envio, "text": message, "delay": 0},
            )
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"[MANUTENCAO:{phone}] UAZAPI erro: {e}")
        await redis.client.set(dedup_key, "1", ex=86400)
        return False

    await redis.client.set(dedup_key, "1", ex=86400)
    logger.info(f"[MANUTENCAO:{phone}] Notificação D-7 enviada (contrato={contract_id})")
    return True


if __name__ == "__main__":
    asyncio.run(run_manutencao())
