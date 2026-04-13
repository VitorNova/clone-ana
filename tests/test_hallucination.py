"""Teste unitário do detector de hallucination (core/hallucination.py).

Valida que a regex com \\b diferencia corretamente:
- "transferi" (passado → hallucination) vs "transferir" (infinitivo → ok)
- "encaminhei" vs "encaminhar"
- "verifiquei" vs "verificar"

Testa tanto a função pública `detectar_hallucination` (com AIMessage reais)
quanto os patterns regex diretamente.
"""

import re
from unittest.mock import MagicMock

from core.hallucination import detectar_hallucination, inferir_destino_do_texto, _HALL_CHECKS


# ── Helpers ──

def _detecta(resposta: str, tool_name: str) -> bool:
    """Testa regex diretamente (sem AIMessage)."""
    resp_lower = resposta.lower()
    for tn, frases in _HALL_CHECKS:
        if tn == tool_name:
            return any(re.search(f, resp_lower) for f in frases)
    return False


def _make_ai_message(content: str, tool_calls=None):
    """Cria AIMessage mock com content e tool_calls."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    type(msg).__name__ = "AIMessage"
    # Para isinstance check funcionar
    return msg


def _patch_isinstance():
    """Patch para isinstance funcionar com mocks no detectar_hallucination."""
    from langchain_core.messages import AIMessage
    return AIMessage


# ── Testes de Regex (unitários puros) ──

def test_hallucination_real_transferi():
    assert _detecta("Já transferi você para o financeiro.", "transferir_departamento")


def test_falso_positivo_transferir():
    assert not _detecta("Posso te transferir para o financeiro?", "transferir_departamento")


def test_hallucination_vou_transferir():
    # "Vou te transferir" sem chamar a tool É hallucination (confirmado em produção 2026-04-13)
    assert _detecta("Vou te transferir para o financeiro, pode ser?", "transferir_departamento")


def test_hallucination_encaminhei():
    assert _detecta("Encaminhei seu caso para o atendimento.", "transferir_departamento")


def test_falso_positivo_encaminhar():
    assert not _detecta("Preciso encaminhar para o financeiro.", "transferir_departamento")


def test_hallucination_te_passo_para():
    assert _detecta("Te passo para o financeiro agora.", "transferir_departamento")


def test_falso_positivo_direcionando():
    assert not _detecta("Estou direcionando seu atendimento.", "transferir_departamento")


def test_hallucination_registrei():
    assert _detecta("Registrei seu compromisso para sexta.", "registrar_compromisso")


def test_falso_positivo_registrar():
    assert not _detecta("Posso registrar um compromisso?", "registrar_compromisso")


def test_hallucination_compromisso_registrado():
    assert _detecta("Compromisso registrado para dia 10.", "registrar_compromisso")


def test_hallucination_verifiquei():
    assert _detecta("Verifiquei aqui e seu pagamento consta.", "consultar_cliente")


def test_falso_positivo_verificar():
    assert not _detecta("Vou verificar seu pagamento.", "consultar_cliente")


def test_hallucination_consultei():
    assert _detecta("Consultei e encontrei 2 faturas.", "consultar_cliente")


def test_falso_positivo_consultar():
    assert not _detecta("Preciso consultar seu CPF.", "consultar_cliente")


def test_hallucination_encontrei_no_sistema():
    assert _detecta("Encontrei no sistema suas cobranças.", "consultar_cliente")


def test_falso_positivo_encontrei_generico():
    assert not _detecta("Não encontrei nada com esse CPF.", "consultar_cliente")


# ── Testes da função detectar_hallucination (integração com AIMessage) ──

def test_detectar_hallucination_com_tool_chamada():
    """Se tool foi chamada, NÃO é hallucination mesmo com texto."""
    from langchain_core.messages import AIMessage

    msg_com_tool = AIMessage(content="", tool_calls=[{"name": "transferir_departamento", "args": {}, "id": "1"}])
    msg_resposta = AIMessage(content="Já transferi você para o financeiro.")
    result = detectar_hallucination([msg_com_tool, msg_resposta], "5565999990000")
    assert "transferir_departamento" not in result


def test_detectar_hallucination_sem_tool_chamada():
    """Se tool NÃO foi chamada mas texto afirma, É hallucination."""
    from langchain_core.messages import AIMessage

    msg = AIMessage(content="Já transferi você para o financeiro.")
    result = detectar_hallucination([msg], "5565999990000")
    assert "transferir_departamento" in result


def test_detectar_hallucination_texto_limpo():
    """Texto normal sem afirmação de ação → sem hallucination."""
    from langchain_core.messages import AIMessage

    msg = AIMessage(content="Olá! Como posso te ajudar?")
    result = detectar_hallucination([msg], "5565999990000")
    assert result == []


def test_detectar_hallucination_mensagem_vazia():
    """Lista vazia → sem hallucination."""
    result = detectar_hallucination([], "5565999990000")
    assert result == []


# ── Testes de inferir_destino_do_texto (contingência hallucination) ──

def test_inferir_destino_financeiro():
    assert inferir_destino_do_texto("Vou transferir para o financeiro verificar") == "financeiro"


def test_inferir_destino_atendimento():
    assert inferir_destino_do_texto("Já encaminhei para o atendimento") == "atendimento"


def test_inferir_destino_cobrancas():
    assert inferir_destino_do_texto("Te transferi para cobranças") == "cobrancas"


def test_inferir_destino_caso_real_575503():
    """Caso real de produção 2026-04-13: 'Vou transferir para lá!' sem setor explícito."""
    result = inferir_destino_do_texto(
        "Como você já efetuou o pagamento, preciso que encaminhe o comprovante para o financeiro verificar, tudo bem? Vou transferir para lá!"
    )
    assert result == "financeiro"


def test_inferir_destino_texto_sem_transferencia():
    assert inferir_destino_do_texto("Olá! Como posso te ajudar?") is None


def test_inferir_destino_fallback_atendimento():
    """Texto com 'transferir' mas sem setor → fallback atendimento."""
    assert inferir_destino_do_texto("Vou transferir para lá!") == "atendimento"


def test_inferir_destino_none():
    assert inferir_destino_do_texto(None) is None


def test_inferir_destino_vazio():
    assert inferir_destino_do_texto("") is None
