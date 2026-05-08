# tests/test_config.py — Unit tests for fault_config (pure in-memory catalog validation)
import json
import os
import tempfile

import agentchaos
from agentchaos import EvalReport, EvalResult, fault_config
from agentchaos.fault_engine import FaultSpec


def test_total_65_experiments():
    assert len(fault_config.EXPERIMENTS) == 65


def test_all_experiments_have_name_and_faults():
    for exp in fault_config.EXPERIMENTS:
        assert "name" in exp
        assert "faults" in exp
        assert len(exp["faults"]) >= 1


def test_all_faults_are_faultspec():
    for exp in fault_config.EXPERIMENTS:
        for spec in exp["faults"]:
            assert isinstance(spec, FaultSpec)


def test_strategies_coverage():
    names = fault_config.list_all()
    for strategy in ["single", "persistent", "intermittent", "burst"]:
        matching = [n for n in names if n.endswith(f"_{strategy}")]
        assert len(matching) == 12  # 6 llm + 6 tool


def test_compound_experiments():
    names = fault_config.list_all()
    compounds = [n for n in names if n.startswith("compound_")]
    assert len(compounds) == 8


def test_positional_experiments():
    names = fault_config.list_all()
    positionals = [n for n in names if "_pos_" in n]
    assert len(positionals) == 9


def test_get_valid():
    exp = fault_config.get("llm_error_single")
    assert exp["name"] == "llm_error_single"
    assert len(exp["faults"]) == 1
    assert exp["faults"][0].action == "set"


def test_get_invalid_raises():
    try:
        fault_config.get("nonexistent_fault")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "nonexistent_fault" in str(e)


def test_list_all_sorted():
    names = fault_config.list_all()
    assert names == sorted(names)


def test_list_by_category_structure():
    cats = fault_config.list_by_category()
    assert "llm" in cats
    assert "tool" in cats
    assert "compound" in cats
    assert len(cats["llm"]) == 6
    assert len(cats["tool"]) == 6
    assert len(cats["compound"]) == 8


def test_list_by_category_has_experiments():
    cats = fault_config.list_by_category()
    for cat_name, items in cats.items():
        for item in items:
            assert "base_name" in item
            assert "type" in item
            assert "description" in item
            assert "experiments" in item


def test_each_experiment_retrievable():
    for name in fault_config.list_all():
        exp = fault_config.get(name)
        assert exp is not None
        assert exp["name"] == name


# ── __init__.py coverage: EvalReport / save_trace branches ────────


def test_eval_report_properties():
    r1 = EvalResult(
        fault="f1",
        result="ok",
        error="",
        passed=True,
        elapsed=0.1,
        faults_fired=0,
        diagnosis={},
        fault_log=[],
    )
    r2 = EvalResult(
        fault="f2",
        result="",
        error="err",
        passed=False,
        elapsed=0.2,
        faults_fired=1,
        diagnosis={},
        fault_log=[],
    )
    report = EvalReport(total=2, passed=1, failed=1, results=[r1, r2])
    assert report.pass_rate == 0.5
    assert report.vulnerable_to == ["f2"]
    assert "1/2" in report.summary()


def test_eval_report_empty():
    report = EvalReport(total=0, passed=0, failed=0, results=[])
    assert report.pass_rate == 0.0
    assert report.vulnerable_to == []
    assert "none" in report.summary()


def test_save_trace_with_fault_data():
    """save_trace correctly writes injected_output when fault was applied."""
    engine = agentchaos.inject("llm_error_single")
    # manually add a trace entry to simulate a faulted call
    engine.trace.append(
        {
            "call_index": 0,
            "request": {"model": "test", "messages": [], "tools": []},
            "response": {
                "content": "original",
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "http_status": 200,
                "modified_content": "[ERROR] injected",
                "modified_tool_calls": [],
            },
            "timing": {"llm_latency_ms": 100, "total_ms": 101},
            "fault": {"applied": True},
        }
    )
    agentchaos.disable()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        agentchaos.save_trace(path)
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["fault_applied"] is True
        assert "injected_output" in data[0]
        assert data[0]["injected_output"]["content"] == "[ERROR] injected"
        assert data[0]["raw_output"]["content"] == "original"
    finally:
        os.unlink(path)


def test_save_trace_no_engine():
    """save_trace with no prior engine does not crash."""
    agentchaos._last_engine = None
    agentchaos.save_trace("/tmp/test_no_engine.json")  # should log error, not crash
