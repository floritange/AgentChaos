# tests/test_core.py — Basic smoke tests for agentchaos SDK
import json
import os
import tempfile

import agentchaos


def test_list_faults_returns_65():
    """All 65 fault configurations are available."""
    faults = agentchaos.list_faults()
    assert len(faults) == 65


def test_get_fault_valid():
    """get_fault returns a valid experiment dict."""
    exp = agentchaos.get_fault("llm_error_single")
    assert "faults" in exp
    assert len(exp["faults"]) >= 1


def test_inject_none_trace_only():
    """inject(None) creates a trace-only engine (no fault specs)."""
    engine = agentchaos.inject(None)
    assert engine is not None
    assert engine.trace_only is True
    agentchaos.disable()


def test_inject_fault():
    """inject(fault_name) creates an engine with fault specs."""
    engine = agentchaos.inject("llm_error_single")
    assert engine is not None
    assert engine.trace_only is False
    agentchaos.disable()


def test_disable_returns_engine():
    """disable() returns the engine that was active."""
    agentchaos.inject(None)
    engine = agentchaos.disable()
    assert engine is not None


def test_save_trace_creates_file():
    """save_trace writes a JSON file."""
    agentchaos.inject(None)
    agentchaos.disable()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        agentchaos.save_trace(path)
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, list)
    finally:
        os.unlink(path)


def test_diagnose():
    """diagnose returns a dict with fault_type key."""
    result = agentchaos.diagnose("Hello world")
    assert "fault_type" in result


def test_list_faults_by_category():
    """list_faults_by_category groups faults correctly."""
    cats = agentchaos.list_faults_by_category()
    assert isinstance(cats, dict)
    assert len(cats) > 0
