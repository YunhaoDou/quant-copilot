"""Lark/Discord webhook push. Same optional-config shape as earnings/wechat_push.py:
a missing webhook URL means the channel is silently skipped, not an error — callers
should treat notification failures as best-effort and never let them break the caller's
main flow (backtest results, paper-trade fills, etc. must persist regardless of whether
the push succeeds).
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def send_lark(text: str) -> bool:
    if not settings.LARK_WEBHOOK_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                settings.LARK_WEBHOOK_URL, json={"msg_type": "text", "content": {"text": text}}
            )
        return resp.status_code == 200
    except httpx.HTTPError as exc:
        logger.warning("Lark push failed: %s", exc)
        return False


async def send_discord(text: str) -> bool:
    if not settings.DISCORD_WEBHOOK_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(settings.DISCORD_WEBHOOK_URL, json={"content": text})
        return resp.status_code in (200, 204)
    except httpx.HTTPError as exc:
        logger.warning("Discord push failed: %s", exc)
        return False


async def notify_all(text: str) -> dict:
    """Fire both channels; each is a no-op if its webhook URL isn't configured."""
    return {"lark": await send_lark(text), "discord": await send_discord(text)}
