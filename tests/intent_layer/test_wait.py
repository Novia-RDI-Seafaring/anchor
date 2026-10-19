"""intents_wait: hold until an intent needs the agent, then claim it (#509)."""
from __future__ import annotations

import asyncio
import json

from intent_layer.actor import Actor, actor_scope
from intent_layer.adapters.mcp import call_tool
from intent_layer.fs_store import FsIntentStore
from intent_layer.service import IntentService
from intent_layer.signals import MemoryPendingSignals
from tests.intent_layer.form_host import FormHost

ME = Actor(kind="agent", label="me")
OTHER = Actor(kind="agent", label="other")
PERSON = Actor(kind="human", label="browser")


def _service(tmp_path):
    return IntentService(FsIntentStore(tmp_path), MemoryPendingSignals(), host=FormHost())


def test_wait_returns_an_ask_filed_while_waiting_through_another_service(tmp_path):
    async def run():
        mine, theirs = _service(tmp_path), _service(tmp_path)  # two processes, one store

        async def file_later():
            await asyncio.sleep(0.2)
            with actor_scope(PERSON):
                await theirs.enqueue("user_request", origin_canvas_id="pumps")

        filer = asyncio.create_task(file_later())
        found = await mine.wait(reader=ME, timeout=3, poll=0.05)
        await filer
        assert found is not None and found.origin_canvas_id == "pumps"
        assert found.claimed_by == ME

    asyncio.run(run())


def test_wait_times_out_with_nothing_to_do(tmp_path):
    assert asyncio.run(_service(tmp_path).wait(reader=ME, timeout=0.1, poll=0.05)) is None


def test_the_agents_own_open_question_does_not_wake_it_but_the_answer_does(tmp_path):
    async def run():
        service = _service(tmp_path)
        with actor_scope(PERSON):
            intent = await service.enqueue("user_request", origin_canvas_id="test")
        with actor_scope(ME):
            _, question = await service.add_item(intent.id, type="question", text="Where is here?")
        assert await service.wait(reader=ME, timeout=0.1, poll=0.05, claim=False) is None
        with actor_scope(PERSON):
            await service.answer_question(intent.id, question.id, text="beside the heading")
        assert (await service.wait(reader=ME, timeout=0.1, poll=0.05)).id == intent.id

    asyncio.run(run())


def test_an_intent_another_agent_holds_is_skipped(tmp_path):
    async def run():
        service = _service(tmp_path)
        with actor_scope(PERSON):
            await service.enqueue("user_request", origin_canvas_id="pumps")
        assert await service.wait(reader=OTHER, timeout=0.1, poll=0.05) is not None
        assert await service.wait(reader=ME, timeout=0.1, poll=0.05) is None
        # The holder itself still gets it back.
        assert await service.wait(reader=OTHER, timeout=0.1, poll=0.05) is not None

    asyncio.run(run())


def test_mcp_intents_wait_reports_a_timeout(tmp_path):
    body = json.loads(asyncio.run(call_tool(
        _service(tmp_path), "intents_wait", {"timeout_s": 0.1}, actor=ME,
    )))
    assert body == {"intent": None, "timed_out": True}
