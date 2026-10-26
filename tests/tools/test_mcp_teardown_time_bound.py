"""A stuck MCP context-manager exit must not wedge transport reconnect."""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from tools import mcp_tool_transport


class _ContextManager:
    def __init__(self, entered, *, hangs=False):
        self.entered = entered
        self.hangs = hangs
        self.exit_started = False

    async def __aenter__(self):
        return self.entered

    async def __aexit__(self, *_exc):
        self.exit_started = True
        if self.hangs:
            await asyncio.Event().wait()
        return False


class _TransportHarness(mcp_tool_transport.MCPServerTransportMixin):
    def __init__(self):
        self.name = "test"

    def _session_kwargs(self):
        return {}

    async def _serve_session(self, *_args):
        return "reconnect"


@pytest.mark.asyncio
@pytest.mark.parametrize("stuck_exit", ["client", "transport"])
async def test_stalled_exit_does_not_block_reconnect(monkeypatch, caplog, stuck_exit):
    transport_cm = _ContextManager((object(), object()), hangs=stuck_exit == "transport")
    client_cm = _ContextManager(None, hangs=stuck_exit == "client")
    monkeypatch.setattr(mcp_tool_transport, "_MCP_TEARDOWN_TIMEOUT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(mcp_tool_transport, "_core", SimpleNamespace(ClientSession=lambda *_a, **_kw: client_cm))

    with caplog.at_level(logging.WARNING, logger="tools.mcp_tool"):
        result = await asyncio.wait_for(
            _TransportHarness()._serve_transport(transport_cm, "HTTP", 1), timeout=0.2
        )

    assert result == "reconnect"
    assert f"{stuck_exit} MCP teardown did not finish" in caplog.text
    assert "abandoned" in caplog.text
    assert client_cm.exit_started
    assert transport_cm.exit_started


@pytest.mark.asyncio
async def test_normal_teardown_is_unchanged(monkeypatch, caplog):
    transport_cm = _ContextManager((object(), object()))
    client_cm = _ContextManager(None)
    monkeypatch.setattr(mcp_tool_transport, "_MCP_TEARDOWN_TIMEOUT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(mcp_tool_transport, "_core", SimpleNamespace(ClientSession=lambda *_a, **_kw: client_cm))

    with caplog.at_level(logging.WARNING, logger="tools.mcp_tool"):
        result = await _TransportHarness()._serve_transport(transport_cm, "HTTP", 1)

    assert result == "reconnect"
    assert not caplog.records
    assert client_cm.exit_started
    assert transport_cm.exit_started


@pytest.mark.asyncio
async def test_sdk_timeout_error_is_not_mistaken_for_our_deadline(monkeypatch, caplog):
    class _SdkTimeout(_ContextManager):
        async def __aexit__(self, *_exc):
            raise TimeoutError("SDK teardown error")

    monkeypatch.setattr(mcp_tool_transport, "_MCP_TEARDOWN_TIMEOUT_SECONDS", 1)
    cm = _SdkTimeout(None)
    bounded = mcp_tool_transport._BoundedAsyncExit(cm, server_name="test", phase="client")

    with caplog.at_level(logging.WARNING, logger="tools.mcp_tool"):
        with pytest.raises(TimeoutError, match="SDK teardown error"):
            await bounded.__aexit__(None, None, None)

    assert not caplog.records
