from __future__ import annotations

import pytest

from citnega.packages.runtime.context.conversation_store import ConversationStore


@pytest.mark.asyncio
async def test_conversation_store_persists_nextgen_session_state(tmp_path):
    session_dir = tmp_path / "sessions" / "sess-1"
    store = ConversationStore(session_dir, default_model_id="model-x")
    await store.load()

    store.set_plan_phase("execute")
    store.set_active_skills(["release", "review"])
    store.set_mental_model_spec({"risk_posture": "conservative"})
    store.set_compiled_plan_metadata({"plan_id": "p1", "step_count": 2})

    restored = ConversationStore(session_dir, default_model_id="model-x")
    await restored.load()

    assert restored.plan_phase == "execute"
    assert restored.active_skills == ["release", "review"]
    assert restored.mental_model_spec == {"risk_posture": "conservative"}
    assert restored.compiled_plan_metadata == {"plan_id": "p1", "step_count": 2}
