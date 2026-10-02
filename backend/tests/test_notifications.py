"""Webhook posts are monkeypatched (no real network / no real webhook secrets needed) —
same style as test_news_sentiment.py's fetch patching.
"""
import pytest

from app.config import settings
from app.services import notifications


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeAsyncClient:
    def __init__(self, status_code: int, calls: list):
        self._status_code = status_code
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json):
        self._calls.append((url, json))
        return _FakeResponse(self._status_code)


@pytest.mark.asyncio
async def test_send_lark_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "LARK_WEBHOOK_URL", "")
    assert await notifications.send_lark("hello") is False


@pytest.mark.asyncio
async def test_send_lark_posts_when_configured(monkeypatch):
    calls: list = []
    monkeypatch.setattr(settings, "LARK_WEBHOOK_URL", "https://open.larksuite.com/fake")
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _FakeAsyncClient(200, calls))
    ok = await notifications.send_lark("hello")
    assert ok is True
    assert calls[0][0] == "https://open.larksuite.com/fake"
    assert calls[0][1]["content"]["text"] == "hello"


@pytest.mark.asyncio
async def test_send_discord_posts_when_configured(monkeypatch):
    calls: list = []
    monkeypatch.setattr(settings, "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/fake")
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _FakeAsyncClient(204, calls))
    ok = await notifications.send_discord("hello")
    assert ok is True
    assert calls[0][1]["content"] == "hello"


@pytest.mark.asyncio
async def test_notify_all_reports_per_channel(monkeypatch):
    monkeypatch.setattr(settings, "LARK_WEBHOOK_URL", "")
    monkeypatch.setattr(settings, "DISCORD_WEBHOOK_URL", "")
    result = await notifications.notify_all("hello")
    assert result == {"lark": False, "discord": False}
