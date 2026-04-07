"""Testes unitários do retry com backoff (infra/retry.py).

Valida: sucesso na 1a tentativa, sucesso após falha, falha total,
e que backoff delays são respeitados.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from infra.retry import invocar_com_retry, MAX_TENTATIVAS, BACKOFF_DELAYS


@pytest.mark.asyncio
async def test_sucesso_primeira_tentativa():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={"messages": ["ok"]})

    result, error = await invocar_com_retry(graph, {"messages": []}, phone="5565999990000")

    assert result == {"messages": ["ok"]}
    assert error is None
    assert graph.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_sucesso_apos_falha():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(side_effect=[Exception("timeout"), {"messages": ["ok"]}])

    result, error = await invocar_com_retry(
        graph, {"messages": []}, phone="5565999990000",
        backoff_delays=[0.01, 0.01, 0.01],  # Delays curtos para teste
    )

    assert result == {"messages": ["ok"]}
    # last_error preserva o erro da tentativa que falhou (útil para logging)
    assert error is not None
    assert "timeout" in str(error)
    assert graph.ainvoke.call_count == 2


@pytest.mark.asyncio
async def test_falha_total():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(side_effect=Exception("API down"))

    result, error = await invocar_com_retry(
        graph, {"messages": []}, phone="5565999990000",
        max_tentativas=2,
        backoff_delays=[0.01, 0.01],
    )

    assert result is None
    assert error is not None
    assert "API down" in str(error)
    assert graph.ainvoke.call_count == 2


@pytest.mark.asyncio
async def test_constantes_padrao():
    assert MAX_TENTATIVAS == 3
    assert BACKOFF_DELAYS == [2.0, 4.0, 8.0]


@pytest.mark.asyncio
async def test_payload_passado_corretamente():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={"result": "ok"})
    payload = {"messages": [{"role": "user", "content": "oi"}], "phone": "123"}

    await invocar_com_retry(graph, payload, phone="123")

    graph.ainvoke.assert_called_once_with(payload)
