import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.telegram import TelegramAdapter


@pytest.mark.asyncio
async def test_telegram_send_and_edit_are_serialized_per_chat():
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="test-token", extra={}))

    active = 0
    max_active = 0
    calls = []

    async def send_message(**kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        calls.append(("send", kwargs["text"]))
        await asyncio.sleep(0.01)
        active -= 1
        return SimpleNamespace(message_id=1)

    async def edit_message_text(**kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        calls.append(("edit", kwargs["text"]))
        await asyncio.sleep(0.01)
        active -= 1
        return SimpleNamespace(message_id=2)

    adapter._bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=send_message),
        edit_message_text=AsyncMock(side_effect=edit_message_text),
    )

    await asyncio.gather(
        adapter._send_message_locked("123", chat_id=123, text="a"),
        adapter._edit_message_text_locked("123", chat_id=123, message_id=1, text="b"),
        adapter._send_message_locked("123", chat_id=123, text="c"),
    )

    assert max_active == 1
    assert calls == [("send", "a"), ("edit", "b"), ("send", "c")]


@pytest.mark.asyncio
async def test_telegram_send_lock_is_per_chat_not_global():
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="test-token", extra={}))

    entered = asyncio.Event()
    release = asyncio.Event()
    chat_2_completed = asyncio.Event()

    async def send_message(**kwargs):
        if kwargs["chat_id"] == 1:
            entered.set()
            await release.wait()
        else:
            chat_2_completed.set()
        return SimpleNamespace(message_id=kwargs["chat_id"])

    adapter._bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=send_message),
        edit_message_text=AsyncMock(),
    )

    task_1 = asyncio.create_task(adapter._send_message_locked("1", chat_id=1, text="slow"))
    await entered.wait()
    await adapter._send_message_locked("2", chat_id=2, text="fast")

    assert chat_2_completed.is_set()
    release.set()
    await task_1
