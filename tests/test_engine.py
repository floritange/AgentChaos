# tests/test_engine.py — Unit tests for FaultEngine (pure in-memory, no network)
import copy

from agentchaos.fault_engine import FaultEngine, FaultSpec, _parse_tokens, jp_get, jp_set

# ── JSON path helpers ─────────────────────────────────────────────

SAMPLE_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": "The answer is 42.",
                "tool_calls": [
                    {"id": "tc_1", "type": "function", "function": {"name": "calc", "arguments": '{"x": 1}'}}
                ],
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def _resp():
    return copy.deepcopy(SAMPLE_RESPONSE)


def test_jp_get_content():
    assert jp_get(SAMPLE_RESPONSE, "$.choices[0].message.content") == "The answer is 42."


def test_jp_get_nested():
    assert jp_get(SAMPLE_RESPONSE, "$.choices[0].finish_reason") == "stop"


def test_jp_get_missing():
    assert jp_get(SAMPLE_RESPONSE, "$.choices[0].message.nonexistent") is None


def test_jp_get_index_out_of_range():
    assert jp_get(SAMPLE_RESPONSE, "$.choices[5].message.content") is None


def test_jp_set_content():
    data = _resp()
    jp_set(data, "$.choices[0].message.content", "modified")
    assert data["choices"][0]["message"]["content"] == "modified"


def test_jp_set_unreachable():
    data = _resp()
    jp_set(data, "$.nonexist[0].field", "value")  # should not crash


# ── FaultEngine basic ─────────────────────────────────────────────


def test_engine_add_and_clear():
    engine = FaultEngine(seed=42)
    engine.add(FaultSpec(intercept="response", action="set", target_path="$.choices[0].message.content", value="err"))
    assert len(engine._faults) == 1
    engine.clear()
    assert len(engine._faults) == 0


def test_engine_trace_only():
    engine = FaultEngine(seed=42, trace_only=True)
    assert engine.has_active_faults() is True
    assert len(engine._faults) == 0


def test_engine_has_active_faults_exhausted():
    engine = FaultEngine(seed=42)
    spec = FaultSpec(intercept="response", action="set", target_path="$", value="x", max_count=1)
    engine.add(spec)
    assert engine.has_active_faults() is True
    spec._count = 1
    assert engine.has_active_faults() is False


# ── FaultEngine.apply — action: set ───────────────────────────────


def test_apply_set_content():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.content",
            value="[ERROR]",
            max_count=1,
            skip_guard=True,
        )
    )
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"
    assert data["choices"][0]["message"]["content"] == "[ERROR]"
    assert delay == 0.0


def test_apply_set_tool_calls_empty():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.tool_calls",
            value=[],
            max_count=1,
        )
    )
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"
    assert data["choices"][0]["message"]["tool_calls"] == []


# ── FaultEngine.apply — action: truncate ──────────────────────────


def test_apply_truncate_content():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="truncate",
            target_path="$.choices[0].message.content",
            value=0.5,
            max_count=1,
            skip_guard=True,
        )
    )
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"
    assert len(data["choices"][0]["message"]["content"]) < len("The answer is 42.")
    assert data["choices"][0]["finish_reason"] == "length"


def test_apply_truncate_tool_arguments():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="truncate",
            target_path="$.choices[0].message.tool_calls[0].function.arguments",
            value=0.5,
            max_count=1,
        )
    )
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"


# ── FaultEngine.apply — action: corrupt ───────────────────────────


def test_apply_corrupt_content():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="corrupt",
            target_path="$.choices[0].message.content",
            value="unicode",
            max_count=1,
            skip_guard=True,
        )
    )
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"
    assert data["choices"][0]["message"]["content"] != "The answer is 42."


def test_apply_corrupt_mojibake():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="corrupt",
            target_path="$.choices[0].message.content",
            value="mojibake",
            max_count=1,
            skip_guard=True,
        )
    )
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"


def test_apply_corrupt_tool_arguments():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="corrupt",
            target_path="$.choices[0].message.tool_calls[0].function.arguments",
            value="unicode",
            max_count=1,
        )
    )
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"


# ── FaultEngine.apply — action: delay ─────────────────────────────


def test_apply_delay():
    engine = FaultEngine(seed=42)
    engine.add(FaultSpec(intercept="response", action="delay", value=2000, max_count=1))
    action, data, delay = engine.apply("response", _resp())
    assert delay == 2000.0
    assert action == "delay"


# ── FaultEngine.apply — action: drop ──────────────────────────────


def test_apply_drop():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="drop",
            target_path="$.choices[0].message.tool_calls[0]",
            max_count=1,
        )
    )
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"
    assert data["choices"][0]["message"]["tool_calls"] == []


# ── FaultEngine.apply — action: error ─────────────────────────────


def test_apply_error():
    engine = FaultEngine(seed=42)
    engine.add(FaultSpec(intercept="response", action="error", value=503, max_count=1))
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"
    assert "503" in data["choices"][0]["message"]["content"]


# ── FaultEngine.apply — action: duplicate ─────────────────────────


def test_apply_duplicate_no_cache():
    engine = FaultEngine(seed=42)
    engine.add(FaultSpec(intercept="response", action="duplicate", max_count=1))
    action, data, delay = engine.apply("response", _resp())
    # no cached response yet, so nothing happens
    assert action == "pass"


def test_apply_duplicate_with_cache():
    engine = FaultEngine(seed=42)
    engine._last_response = {"choices": [{"message": {"content": "cached"}, "finish_reason": "stop"}]}
    engine.add(FaultSpec(intercept="response", action="duplicate", max_count=1))
    action, data, delay = engine.apply("response", _resp())
    assert action == "modify"
    assert data["choices"][0]["message"]["content"] == "cached"


# ── FaultEngine.apply — guard logic ──────────────────────────────


def test_guard_skips_content_fault_when_tool_calls_present():
    """Content fault should NOT fire when tool_calls are present (guard active)."""
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.content",
            value="[ERROR]",
            max_count=1,
            skip_guard=False,
        )
    )
    action, data, delay = engine.apply("response", _resp())
    assert action == "pass"  # guard prevents firing


def test_guard_skips_tool_fault_when_no_tool_calls():
    """Tool fault should NOT fire when tool_calls are empty (guard active)."""
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.tool_calls",
            value=[],
            max_count=1,
            skip_guard=False,
        )
    )
    resp = _resp()
    resp["choices"][0]["message"]["tool_calls"] = []
    action, data, delay = engine.apply("response", resp)
    assert action == "pass"


# ── FaultEngine.apply — probability and count ─────────────────────


def test_max_count_exhaustion():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.content",
            value="X",
            max_count=1,
            skip_guard=True,
        )
    )
    engine.apply("response", _resp())  # fires
    action, data, delay = engine.apply("response", _resp())  # exhausted
    assert action == "pass"


def test_min_count_delayed_onset():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.content",
            value="X",
            max_count=2,
            min_count=1,
            skip_guard=True,
        )
    )
    action1, _, _ = engine.apply("response", _resp())  # count=1, but min_count=1, skip
    assert action1 == "pass"
    action2, data2, _ = engine.apply("response", _resp())  # count=2, fires
    assert action2 == "modify"
    assert data2["choices"][0]["message"]["content"] == "X"


def test_probability_zero_never_fires():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.content",
            value="X",
            probability=0.0,
            skip_guard=True,
        )
    )
    action, _, _ = engine.apply("response", _resp())
    assert action == "pass"


# ── _parse_tokens edge cases ──────────────────────────────────────


def test_parse_tokens_root():
    assert _parse_tokens("$") == []
    assert _parse_tokens("") == []


def test_parse_tokens_numeric_segment():
    tokens = _parse_tokens("$.items.0.name")
    assert 0 in tokens
    assert "name" in tokens


# ── _truncate_json_values / _corrupt_json_values edge cases ───────


def test_truncate_json_values_invalid_json():
    engine = FaultEngine(seed=42)
    result = engine._truncate_json_values("not valid json{{{", 0.5)
    assert "_fault_truncated" in result


def test_truncate_json_values_nested():
    engine = FaultEngine(seed=42)
    result = engine._truncate_json_values('{"key": "longvalue", "nested": {"a": "hello"}}', 0.5)
    data = __import__("json").loads(result)
    assert len(data["key"]) <= len("longvalue")


def test_corrupt_json_values_invalid_json():
    engine = FaultEngine(seed=42)
    result = engine._corrupt_json_values("not valid json{{{")
    assert "_fault_corrupted" in result


def test_corrupt_json_values_nested():
    engine = FaultEngine(seed=42)
    result = engine._corrupt_json_values('{"key": "hello world"}')
    data = __import__("json").loads(result)
    assert data["key"] != "hello world"


# ── corrupt broken_json mode ─────────────────────────────────────


def test_apply_corrupt_broken_json():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="corrupt",
            target_path="$.choices[0].message.content",
            value="broken_json",
            max_count=1,
            skip_guard=True,
        )
    )
    action, data, _ = engine.apply("response", _resp())
    assert action == "modify"
    assert "\x00" in data["choices"][0]["message"]["content"]


# ── truncate on list target ───────────────────────────────────────


def test_apply_truncate_list():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="truncate",
            target_path="$.choices[0].message.tool_calls",
            value=0.5,
            max_count=1,
        )
    )
    resp = _resp()
    resp["choices"][0]["message"]["tool_calls"] = [{"id": "1"}, {"id": "2"}, {"id": "3"}, {"id": "4"}]
    action, data, _ = engine.apply("response", resp)
    assert action == "modify"
    assert len(data["choices"][0]["message"]["tool_calls"]) == 2


# ── corrupt on empty string target (no-op) ────────────────────────


def test_apply_corrupt_empty_string():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="corrupt",
            target_path="$.choices[0].message.content",
            value="unicode",
            max_count=1,
            skip_guard=True,
        )
    )
    resp = _resp()
    resp["choices"][0]["message"]["content"] = ""
    action, data, _ = engine.apply("response", resp)
    # empty string can't be corrupted, action stays pass
    assert action == "pass"


# ── truncate on empty string (no-op) ─────────────────────────────


def test_apply_truncate_empty_string():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="response",
            action="truncate",
            target_path="$.choices[0].message.content",
            value=0.3,
            max_count=1,
            skip_guard=True,
        )
    )
    resp = _resp()
    resp["choices"][0]["message"]["content"] = ""
    action, data, _ = engine.apply("response", resp)
    assert action == "pass"


# ── intercept mismatch (request spec on response) ────────────────


def test_apply_intercept_mismatch():
    engine = FaultEngine(seed=42)
    engine.add(
        FaultSpec(
            intercept="request",
            action="set",
            target_path="$.choices[0].message.content",
            value="X",
            max_count=1,
            skip_guard=True,
        )
    )
    action, _, _ = engine.apply("response", _resp())
    assert action == "pass"
