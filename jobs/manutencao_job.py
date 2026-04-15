"""Job de Manutenção Preventiva — Arquivo único (disparo D-7).

Este arquivo reúne TODO o código necessário para disparar o lembrete de
manutenção preventiva D-7. Em vez de depender de infra/* e core/*, tudo
que é usado está inline neste arquivo.

Escopo: disparo. A parte de resposta do cliente (grafo LangGraph, tools,
context_detector, prompt, webhook) continua fora — ela roda no agente Ana.

Uso:
    python jobs/manutencao_job.py
    PM2 cron: seg-sex às 9h (ecosystem.config.js)
"""

# Importa as bibliotecas necessárias — linha 16 até 33 (boilerplate, não requer validação)
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import redis as sync_redis
import redis.asyncio as async_redis
from dotenv import load_dotenv
from supabase import Client, create_client

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

# Configura o sistema de logs — linha 35 até 40 (boilerplate, não requer validação)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Constantes centralizadas (antes em core/constants.py) — linha 42 até 56 (não validado)
TABLE_LEADS = "ana_leads"
TABLE_ASAAS_CLIENTES = "asaas_clientes"
TABLE_CONTRACT_DETAILS = "contract_details"
TABLE_INCIDENTES = "ana_incidentes"

LEADBOX_API_URL = os.environ.get("LEADBOX_API_URL", "https://enterprise-135api.leadbox.app.br")
LEADBOX_API_UUID = os.environ.get("LEADBOX_API_UUID", "")
LEADBOX_API_TOKEN = os.environ.get("LEADBOX_API_TOKEN", "")
LEADBOX_EXTERNAL_URL = f"{LEADBOX_API_URL}/v1/api/external/{LEADBOX_API_UUID}/"

QUEUE_MANUTENCAO = 545
USER_IA = 1095
AGENT_ID = os.environ.get("AGENT_ID", "ana-langgraph")
AGENT_NAME = "Ana"

# Mensagem que o cliente recebe no WhatsApp — linha 58 até 66 (não validado)
TEMPLATE = (
    "Olá, {nome}!\n\n"
    "Está chegando a hora da manutenção preventiva do seu ar-condicionado!\n\n"
    "*Equipamento:* {equipamento}\n"
    "*Endereço:* {endereco}\n\n"
    "A manutenção é gratuita e está inclusa no seu contrato.\n\n"
    "Quer agendar? Me fala um dia e horário de preferência!"
)

# Cliente Supabase singleton (antes em infra/supabase.py) — linha 68 até 90 (validado)
_supabase_client: Optional[Client] = None


def get_supabase() -> Optional[Client]:
    """Retorna client Supabase singleton. None se SUPABASE_URL/KEY faltarem."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        logger.warning("[SUPABASE] URL ou KEY não configurados")
        return None
    try:
        _supabase_client = create_client(url, key)
        logger.info("[SUPABASE] Conectado")
        return _supabase_client
    except Exception as e:
        logger.error(f"[SUPABASE] Erro: {e}", exc_info=True)
        return None


# Event logger inline (antes em infra/event_logger.py) — linha 92 até 130 (validado)
LOGS_DIR = Path(__file__).parent.parent / "logs"
EVENTS_FILE = LOGS_DIR / "events.jsonl"
TIMEZONE_OFFSET = -4  # UTC-4 Mato Grosso


def log_event(event_type: str, phone: str = "", **kwargs):
    """Append de um evento estruturado em logs/events.jsonl."""
    try:
        LOGS_DIR.mkdir(exist_ok=True)
        if EVENTS_FILE.exists() and EVENTS_FILE.stat().st_size > 5 * 1024 * 1024:
            _rotate_events()

        now = datetime.now(timezone(timedelta(hours=TIMEZONE_OFFSET)))
        entry = {
            "ts": now.isoformat(),
            "type": event_type,
            "phone": phone[-8:] if phone else "",
            **kwargs,
        }
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[EVENT_LOG] Falha ao salvar evento: {e}")


def _rotate_events():
    """Rotaciona events.jsonl quando passa de 5MB; apaga arquivos > 30 dias."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        archive = LOGS_DIR / f"events.{today}.jsonl"
        EVENTS_FILE.rename(archive)
        cutoff = datetime.now() - timedelta(days=30)
        for f in LOGS_DIR.glob("events.*.jsonl"):
            if f.stat().st_mtime < cutoff.timestamp():
                f.unlink()
    except Exception as e:
        logger.warning(f"[EVENT_LOG] Erro na rotação: {e}")


# Registro de incidentes (antes em infra/incidentes.py) — linha 132 até 157 (validado)
def registrar_incidente(telefone: str, tipo: str, detalhe: str = "", contexto: dict = None):
    """Salva falha na tabela ana_incidentes.

    Tipos usados por este arquivo:
        manutencao_erro  — falha genérica no disparo
        envio_falhou     — POST Leadbox falhou
        upsert_lead_erro — INSERT/UPDATE de lead falhou
        marker_ia_falhou — não conseguiu gravar marker anti-eco
    """
    try:
        sb = get_supabase()
        if not sb:
            logger.warning(f"[INCIDENTE] Supabase indisponível: {tipo} phone={telefone}")
            return
        phone_clean = "".join(filter(str.isdigit, telefone))
        sb.table(TABLE_INCIDENTES).insert({
            "telefone": phone_clean,
            "tipo": tipo,
            "detalhe": detalhe[:500] if detalhe else "",
            "contexto": contexto or {},
        }).execute()
        logger.info(f"[INCIDENTE] Registrado: {tipo} phone={phone_clean}")
    except Exception as e:
        logger.warning(f"[INCIDENTE] Falha ao registrar {tipo}: {e}")


# Redis service mínimo (antes em infra/redis.py) — linha 159 até 196 (validado)
class RedisService:
    """Redis async com o mínimo que o job precisa: is_paused + lock + client bruto."""

    def __init__(self, url: str = None):
        self._url = url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self._client: Optional[async_redis.Redis] = None

    async def connect(self):
        if self._client is None:
            self._client = async_redis.from_url(self._url, encoding="utf-8", decode_responses=True)
            await self._client.ping()
            logger.info("[REDIS] Conectado")

    @property
    def client(self) -> async_redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis não conectado. Chame connect() primeiro.")
        return self._client

    def _pause_key(self, phone: str) -> str:
        return f"pause:{AGENT_ID}:{phone}"

    async def is_paused(self, phone: str) -> bool:
        return await self.client.exists(self._pause_key(phone)) > 0


_redis_service: Optional[RedisService] = None


async def get_redis_service() -> RedisService:
    """Singleton — conecta na primeira chamada."""
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
        await _redis_service.connect()
    return _redis_service


# Client Leadbox + marker anti-eco (antes em infra/leadbox_client.py) — linha 198 até 255 (validado)
_sync_pool: Optional[sync_redis.Redis] = None


def _get_sync_redis() -> sync_redis.Redis:
    """Pool Redis sync para gravar o marker anti-eco sem usar async."""
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = sync_redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
    return _sync_pool


def _mark_sent_by_ia(phone: str):
    """Grava marker no Redis para diferenciar eco da IA de mensagem humana."""
    try:
        r = _get_sync_redis()
        r.set(f"sent:ia:{AGENT_ID}:{phone}", "1", ex=15)
    except Exception as e:
        logger.warning(f"[LEADBOX] Falha ao marcar sent:ia para {phone}: {e}")
        registrar_incidente(phone, "marker_ia_falhou", str(e)[:300])


def enviar_resposta_leadbox(phone: str, mensagem: str, raw: bool = False,
                            queue_id: int = None, user_id: int = None) -> bool:
    """POST Leadbox (texto livre). raw=True envia sem prefixo *Ana:* (usado por este job)."""
    if not LEADBOX_API_TOKEN:
        logger.warning("[LEADBOX] LEADBOX_API_TOKEN não configurado, pulando envio")
        return False

    body = mensagem if raw else f"*{AGENT_NAME}:*\n{mensagem}"
    payload = {"body": body, "number": phone, "externalKey": phone}
    if queue_id is not None:
        payload["queueId"] = queue_id
        payload["forceTicketToDepartment"] = True
    if user_id is not None:
        payload["userId"] = user_id
        payload["forceTicketToUser"] = True

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
            _mark_sent_by_ia(phone)
            return True
    except Exception as e:
        logger.error("[LEADBOX] Erro ao enviar resposta para %s: %s", phone, e, exc_info=True)
        registrar_incidente(phone, "envio_falhou", str(e)[:300], {"payload_size": len(mensagem)})
        return False


# Upsert de lead (antes em infra/nodes_supabase.py) — linha 257 até 291 (validado)
def upsert_lead(telefone: str, nome: str = None) -> Optional[str]:
    """Cria ou atualiza lead em ana_leads. Retorna lead_id."""
    supabase = get_supabase()
    if not supabase:
        return None

    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = supabase.table(TABLE_LEADS) \
            .select("id").eq("telefone", telefone).execute()

        if existing.data:
            lead_id = existing.data[0]["id"]
            update = {"last_interaction_at": now, "updated_at": now}
            if nome:
                update["nome"] = nome
            supabase.table(TABLE_LEADS).update(update).eq("id", lead_id).execute()
            return lead_id

        result = supabase.table(TABLE_LEADS).insert({
            "telefone": telefone,
            "nome": nome or f"Lead {telefone}",
            "current_state": "ai",
            "responsavel": "AI",
            "last_interaction_at": now,
            "created_at": now,
            "updated_at": now,
        }).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        logger.error(f"[PERSISTENCIA] Erro upsert_lead: {e}", exc_info=True)
        registrar_incidente(telefone, "upsert_lead_erro", str(e)[:300])
        return None


# Busca contratos com manutenção em 7 dias e monta a mensagem — linha 293 até 365 (query, filtro status, fallback telefone: validados | montagem mensagem: não validado)
def buscar_contratos_d7(hoje: date) -> list:
    """Busca contratos com proxima_manutencao = hoje + 7."""
    supabase = get_supabase()
    if not supabase:
        return []

    data_alvo = (hoje + timedelta(days=7)).isoformat()

    try:
        result = supabase.table(TABLE_CONTRACT_DETAILS).select(
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
            if contrato.get("maintenance_status") == "notified":
                continue

            phone = contrato.get("locatario_telefone")
            if not phone:
                customer_id = contrato.get("customer_id")
                if customer_id:
                    cliente = supabase.table(TABLE_ASAAS_CLIENTES).select(
                        "mobile_phone"
                    ).eq("id", customer_id).limit(1).execute()
                    if cliente.data:
                        phone = cliente.data[0].get("mobile_phone")

            if not phone or len(phone) < 10:
                logger.warning(f"[MANUTENCAO] Contrato {contrato['id']} sem telefone válido")
                continue

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
                nome=nome.split()[0] if nome else "Cliente",
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

    except Exception:
        logger.exception("[MANUTENCAO] Falha ao buscar contratos")
        return []


# Função principal que roda o job de manutenção — linha 367 até 405 (não validado)
async def run_manutencao():
    """Entry point do job: adquire lock, busca elegíveis, dispara notificações."""
    hoje = date.today()
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
                logger.error(f"[MANUTENCAO] Erro: {e}", exc_info=True)
                registrar_incidente(
                    item.get("phone", "?"),
                    "manutencao_erro",
                    str(e)[:300],
                    {"contract_id": item.get("contract_id")},
                )

        logger.info(f"[MANUTENCAO] Concluído: enviados={enviados} erros={erros}")

    finally:
        await redis.client.delete(lock_key)


# Processa e envia uma notificação para cada cliente — linha 407 até 502 (validado)
async def _processar_notificacao(item: dict, redis: RedisService) -> bool:
    """Processa uma notificação D-7: pausa, dedupe, contexto, envio, marca contrato."""
    phone = item["phone"]
    message = item["message"]
    contract_id = item["contract_id"]
    context_type = item["context_type"]

    if await redis.is_paused(phone):
        logger.info(f"[MANUTENCAO:{phone}] Pausado, adiando")
        return False

    dedup_key = f"dispatch:{phone}:{context_type}:{contract_id}:{date.today().isoformat()}"
    if await redis.client.exists(dedup_key):
        logger.info(f"[MANUTENCAO:{phone}] Já notificou hoje")
        return False

    # Salvar contexto ANTES de enviar (validado)
    supabase = get_supabase()
    if not supabase:
        return False

    now = datetime.now(timezone.utc).isoformat()
    clean_phone = "".join(filter(str.isdigit, phone))

    # Buscar lead existente (telefone com/sem DDI 55)
    lead = None
    for tel in [clean_phone, clean_phone[2:] if clean_phone.startswith("55") else f"55{clean_phone}"]:
        result = supabase.table(TABLE_LEADS).select(
            "id, conversation_history"
        ).eq("telefone", tel).limit(1).execute()
        if result.data:
            lead = result.data[0]
            break

    if not lead:
        lead_id = upsert_lead(clean_phone)
        if lead_id:
            # Lead novo: inicializar histórico com role:user para coerência (validado)
            init_history = {"messages": [{
                "role": "user",
                "content": "Oi",
                "timestamp": now,
            }]}
            supabase.table(TABLE_LEADS).update({
                "conversation_history": init_history,
                "updated_at": now,
            }).eq("id", lead_id).execute()

            result = supabase.table(TABLE_LEADS).select(
                "id, conversation_history"
            ).eq("id", lead_id).limit(1).execute()
            if result.data:
                lead = result.data[0]

    if not lead:
        logger.warning(f"[MANUTENCAO:{phone}] Lead não encontrado/criado")
        return False

    # Salvar contexto role:model no histórico (validado)
    history = lead.get("conversation_history") or {"messages": []}
    history["messages"].append({
        "role": "model",
        "content": message,
        "timestamp": now,
        "context": context_type,
        "contract_id": contract_id,
    })

    supabase.table(TABLE_LEADS).update({
        "conversation_history": history,
        "updated_at": now,
    }).eq("id", lead["id"]).execute()

    # Marcar contrato como notificado
    try:
        supabase.table(TABLE_CONTRACT_DETAILS).update({
            "maintenance_status": "notified",
            "notificacao_enviada_at": now,
        }).eq("id", contract_id).execute()
    except Exception as e:
        logger.warning(f"[MANUTENCAO:{phone}] Erro ao marcar contrato: {e}")

    # Enviar via Leadbox (validado)
    tel_envio = clean_phone if clean_phone.startswith("55") else f"55{clean_phone}"
    if not enviar_resposta_leadbox(tel_envio, message, raw=True,
                                    queue_id=QUEUE_MANUTENCAO, user_id=USER_IA):
        logger.error(f"[MANUTENCAO:{phone}] Leadbox erro ao enviar")
        await redis.client.set(dedup_key, "1", ex=86400)
        return False

    await redis.client.set(dedup_key, "1", ex=86400)
    logger.info(f"[MANUTENCAO:{phone}] Notificação D-7 enviada (contrato={contract_id})")
    log_event("manutencao_sent", phone, contract_id=contract_id)
    return True


# Detector de contexto no histórico (antes em core/context_detector.py) — linha 504 até 565 (validado)
CONTEXT_MAPPING = {
    "manutencao_preventiva": "manutencao",
    "disparo_manutencao": "manutencao",
    "manutencao": "manutencao",
}


def detect_context(conversation_history: dict, max_age_hours: int = 168):
    """Varre últimas 10 mensagens do histórico buscando campo `context`.

    Retorna (tipo, reference_id) ou (None, None). Mensagens mais antigas que
    `max_age_hours` (default 168h = 7 dias) são ignoradas.
    """
    messages = (conversation_history or {}).get("messages", [])
    if not messages:
        return None, None

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)

    for msg in reversed(messages[-10:]):
        raw_context = msg.get("context")
        if not raw_context:
            continue
        ts_str = msg.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
        context_type = CONTEXT_MAPPING.get(raw_context, raw_context)
        reference_id = (
            msg.get("reference_id")
            or msg.get("contract_id")
            or msg.get("payment_id")
        )
        logger.info(f"[CONTEXT] Detectado: {context_type} (ref={reference_id})")
        return context_type, reference_id

    return None, None


def build_context_prompt(context_type: str, reference_id: str = None) -> str:
    """Gera trecho de system prompt quando o contexto ativo é manutenção."""
    if context_type != "manutencao":
        return ""
    return f"""## CONTEXTO ATIVO: MANUTENÇÃO PREVENTIVA
O cliente recebeu aviso de manutenção preventiva (contrato: {reference_id or 'N/A'}).
Ele está respondendo sobre AGENDAMENTO DE MANUTENÇÃO.

REGRAS PARA ESTE CONTEXTO:
- NÃO peça CPF — o lead já está identificado
- Se o cliente mencionar DEFEITO (ar fazendo barulho, pingando, não gelando, parou, quebrado, não liga, não esfria, vazando) → transfira para Atendimento/Nathália (fila 453, atendente 815) IMEDIATAMENTE. NÃO peça CPF, NÃO consulte. Apenas transfira. Defeito NÃO é manutenção preventiva.
- Se NÃO for defeito → pergunte dia e horário de preferência para a visita técnica
- Se quiser reagendar → pergunte novo dia/horário
- Se RECUSAR a manutenção ("não preciso", "não quero", "tá tudo ok", "não") → transfira para Atendimento/Nathália (fila 453, atendente 815) IMEDIATAMENTE, sem insistir. A empresa precisa registrar a recusa.
- Manutenção preventiva é GRATUITA (inclusa no contrato)
"""


# Persistência de histórico (antes em infra/nodes_supabase.py) — linha 567 até 739 (validado)
def salvar_mensagem(telefone: str, content: str, direction: str, lead_id: str = None):
    """Append no conversation_history. direction='incoming' → role:user; outros → role:model."""
    supabase = get_supabase()
    if not supabase:
        return

    role = "user" if direction == "incoming" else "model"
    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = supabase.table(TABLE_LEADS) \
            .select("id, conversation_history") \
            .eq("telefone", telefone).limit(1).execute()
        if not existing.data:
            return
        new_msg = {"role": role, "content": content, "timestamp": now}
        history = existing.data[0].get("conversation_history") or {"messages": []}
        history["messages"].append(new_msg)
        supabase.table(TABLE_LEADS) \
            .update({"conversation_history": history, "updated_at": now}) \
            .eq("id", existing.data[0]["id"]).execute()
    except Exception as e:
        logger.error(f"[PERSISTENCIA] Erro salvar_mensagem: {e}", exc_info=True)
        registrar_incidente(telefone, "salvar_msg_erro", str(e)[:300])


def buscar_historico(telefone: str, limite: int = 20):
    """Busca últimas N mensagens como objetos LangChain (HumanMessage/AIMessage/ToolMessage).

    Inclui validação de sequência: remove ToolMessage órfãs e blocos
    incompletos de tool_calls que o Gemini rejeitaria.

    Import de langchain é local porque ele só é necessário quando o grafo
    roda — o disparo D-7 puro não depende disso.
    """
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

    supabase = get_supabase()
    if not supabase:
        return []
    try:
        result = supabase.table(TABLE_LEADS) \
            .select("conversation_history") \
            .eq("telefone", telefone).limit(1).execute()
        if not result.data:
            return []
        history = result.data[0].get("conversation_history") or {"messages": []}
        messages = history.get("messages", [])[-limite:]

        lang_msgs = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "user":
                lang_msgs.append(HumanMessage(content=content))
            elif role == "model":
                tool_calls = m.get("tool_calls")
                if tool_calls:
                    lang_msgs.append(AIMessage(content=content, tool_calls=tool_calls))
                else:
                    # Sanitizar tool-as-text: Gemini 2.0 Flash às vezes escreve
                    # nome de tool como texto no content. Limpar pra não contaminar.
                    if ("transferir_departamento(" in content
                        or "consultar_cliente(" in content
                        or "registrar_compromisso(" in content):
                        content = ""
                    lang_msgs.append(AIMessage(content=content))
            elif role == "tool":
                lang_msgs.append(ToolMessage(
                    content=content,
                    name=m.get("tool_name", ""),
                    tool_call_id=m.get("tool_call_id", "unknown"),
                ))

        # Valida sequência: AIMessage(tool_calls) → ToolMessage(s) correspondentes
        validated: list = []
        pending_tool_ids: set = set()
        for msg in lang_msgs:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                if pending_tool_ids:
                    while validated and (
                        isinstance(validated[-1], ToolMessage)
                        or (isinstance(validated[-1], AIMessage) and validated[-1].tool_calls)
                    ):
                        validated.pop()
                    pending_tool_ids.clear()
                pending_tool_ids = {tc["id"] for tc in msg.tool_calls if "id" in tc}
                validated.append(msg)
            elif isinstance(msg, ToolMessage):
                if pending_tool_ids:
                    validated.append(msg)
                    pending_tool_ids.discard(getattr(msg, "tool_call_id", ""))
            else:
                if pending_tool_ids:
                    while validated and (
                        isinstance(validated[-1], ToolMessage)
                        or (isinstance(validated[-1], AIMessage) and validated[-1].tool_calls)
                    ):
                        validated.pop()
                    pending_tool_ids.clear()
                validated.append(msg)
        if pending_tool_ids:
            while validated and (
                isinstance(validated[-1], ToolMessage)
                or (isinstance(validated[-1], AIMessage) and validated[-1].tool_calls)
            ):
                validated.pop()
        return validated
    except Exception as e:
        logger.error(f"[PERSISTENCIA] Erro buscar_historico: {e}", exc_info=True)
        registrar_incidente(telefone, "historico_busca_erro", str(e)[:300])
        return []


def salvar_mensagens_agente(telefone: str, mensagens: list, usage: dict = None):
    """Salva AIMessage/ToolMessage do LangChain no conversation_history.

    `usage` opcional grava token_count na última AIMessage com texto (para custo).
    """
    from langchain_core.messages import AIMessage, ToolMessage

    supabase = get_supabase()
    if not supabase:
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        result = supabase.table(TABLE_LEADS) \
            .select("id, conversation_history") \
            .eq("telefone", telefone).limit(1).execute()
        if not result.data:
            return
        lead = result.data[0]
        history = lead.get("conversation_history") or {"messages": []}

        last_text_ai_idx = None
        for i, msg in enumerate(mensagens):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                last_text_ai_idx = i

        for i, msg in enumerate(mensagens):
            if isinstance(msg, AIMessage):
                raw = msg.content
                if isinstance(raw, list):
                    text = " ".join(
                        block["text"] for block in raw
                        if isinstance(block, dict) and block.get("text")
                    )
                else:
                    text = raw or ""
                entry = {"role": "model", "content": text, "timestamp": now}
                if msg.tool_calls:
                    entry["tool_calls"] = msg.tool_calls
                if usage and usage.get("total") and i == last_text_ai_idx:
                    entry["token_count"] = usage["total"]
                history["messages"].append(entry)
            elif isinstance(msg, ToolMessage):
                history["messages"].append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_name": msg.name,
                    "tool_call_id": msg.tool_call_id,
                    "timestamp": now,
                })

        supabase.table(TABLE_LEADS).update({
            "conversation_history": history,
            "updated_at": now,
            "last_interaction_at": now,
        }).eq("id", lead["id"]).execute()
    except Exception as e:
        logger.error(f"[PERSISTENCIA] Erro salvar_mensagens_agente: {e}", exc_info=True)
        registrar_incidente(telefone, "historico_erro", f"salvar_mensagens_agente: {e}"[:300])


# Executa o job quando o arquivo é rodado diretamente — linha 741 até 742 (boilerplate, não requer validação)
if __name__ == "__main__":
    asyncio.run(run_manutencao())
