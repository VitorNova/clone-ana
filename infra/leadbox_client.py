"""Client Leadbox — envio de mensagens via API externa.

Extraído de api/webhooks/leadbox.py para eliminar acoplamento circular.
"""

import logging
import os

import httpx
import redis as sync_redis

from core.constants import LEADBOX_API_URL, LEADBOX_API_UUID, LEADBOX_API_TOKEN

logger = logging.getLogger(__name__)

# URL de envio (API externa Leadbox)
LEADBOX_EXTERNAL_URL = f"{LEADBOX_API_URL}/v1/api/external/{LEADBOX_API_UUID}/"

AGENT_NAME = "Ana"

# Pool Redis sync compartilhado (singleton)
_sync_pool = None


def _get_sync_redis() -> sync_redis.Redis:
    """Retorna pool Redis sync singleton."""
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = sync_redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
    return _sync_pool


def enviar_resposta_leadbox(phone: str, mensagem: str, raw: bool = False) -> bool:
    """Envia resposta da IA ao cliente via API externa do Leadbox.

    Args:
        phone: Telefone do destinatário.
        mensagem: Texto da mensagem.
        raw: Se True, envia a mensagem exatamente como está (sem prefixo *Ana:*).
             Usar para templates de billing/manutenção que precisam bater exatamente
             com o template aprovado do WhatsApp.
    """
    if not LEADBOX_API_TOKEN:
        logger.warning("[LEADBOX] LEADBOX_API_TOKEN não configurado, pulando envio")
        return False

    # Assinatura do agente (só para respostas conversacionais, não templates)
    body = mensagem if raw else f"*{AGENT_NAME}:*\n{mensagem}"

    payload = {
        "body": body,
        "number": phone,
        "externalKey": phone,
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                LEADBOX_EXTERNAL_URL,
                params={"token": LEADBOX_API_TOKEN},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            logger.info("[LEADBOX] Resposta enviada para %s", phone)
            # Marker para ignorar eco fromMe (webhook volta com a msg da IA)
            _mark_sent_by_ia(phone)
            return True
    except Exception as e:
        logger.error("[LEADBOX] Erro ao enviar resposta para %s: %s", phone, e, exc_info=True)
        from infra.incidentes import registrar_incidente
        registrar_incidente(phone, "envio_falhou", str(e)[:300], {"payload_size": len(mensagem)})
        return False


def mover_para_fila(phone: str, queue_id: int, user_id: int) -> bool:
    """Move ticket do lead para uma fila no Leadbox (sem enviar mensagem visível)."""
    if not LEADBOX_API_TOKEN:
        return False

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                LEADBOX_EXTERNAL_URL,
                params={"token": LEADBOX_API_TOKEN},
                headers={"Content-Type": "application/json"},
                json={
                    "number": phone,
                    "externalKey": phone,
                    "body": "",
                    "queueId": queue_id,
                    "userId": user_id,
                    "forceTicketToDepartment": True,
                    "forceTicketToUser": True,
                },
            )
            resp.raise_for_status()
            logger.info(f"[LEADBOX] Movido {phone} → fila {queue_id} user {user_id}")
            _mark_sent_by_ia(phone)
            return True
    except Exception as e:
        logger.error(f"[LEADBOX] Falha ao mover {phone} → fila {queue_id}: {e}")
        return False


def _mark_sent_by_ia(phone: str):
    """Grava marker no Redis para diferenciar eco da IA de mensagem humana."""
    try:
        r = _get_sync_redis()
        agent_id = os.environ.get("AGENT_ID", "ana-langgraph")
        r.set(f"sent:ia:{agent_id}:{phone}", "1", ex=15)
    except Exception as e:
        logger.warning(f"[LEADBOX] Falha ao marcar sent:ia para {phone}: {e}")
