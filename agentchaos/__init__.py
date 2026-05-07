# agentchaos — Chaos engineering for robust agent evaluation
#
# Non-intrusive: your agent code needs ZERO changes.
# One line to inject, one line to disable.
#
# Usage:
#   import agentchaos
#
#   agentchaos.inject("llm_error_single")       # inject fault + trace
#   result = await my_agent(query)              # agent runs normally, unaware
#   agentchaos.disable()                        # disable
#   agentchaos.save_trace("trace.json")         # save trace
#
#   agentchaos.inject(None)                     # trace only, no fault
#   result = await my_agent(query)
#   agentchaos.disable()
#   agentchaos.save_trace("trace_normal.json")
#
#   # Batch robustness evaluation:
#   report = await agentchaos.eval(my_agent, "Write a prime checker")
#   print(report.summary())
import copy
import json
import os
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Union

from loguru import logger

from . import fault_config
from .fault_diagnose import diagnose
from .fault_engine import FaultEngine, FaultSpec, install, uninstall

# ══════════════════════════════════════════════════════════════════
# Core API: inject / disable / save_trace
# ══════════════════════════════════════════════════════════════════

_engine: Optional[FaultEngine] = None
_last_engine: Optional[FaultEngine] = None


def inject(fault: Optional[str] = None, seed: int = 42) -> FaultEngine:
    """Start fault injection + trace recording. One line.

    Args:
        fault: fault experiment name (e.g. "llm_error_single"), or None for trace-only mode.
        seed: random seed for reproducibility.
    """
    global _engine
    if fault is None:
        # trace-only mode: record all LLM calls, inject nothing
        engine = FaultEngine(seed=seed, trace_only=True)
    else:
        exp = fault_config.get(fault)
        engine = FaultEngine(seed=seed)
        for spec in exp["faults"]:
            engine.add(copy.deepcopy(spec))
    install(engine)
    _engine = engine
    return engine


def disable() -> Optional[FaultEngine]:
    """Stop injection and trace recording. One line."""
    global _engine, _last_engine
    engine = _engine
    uninstall()
    _engine = None
    _last_engine = engine
    if engine:
        logger.info(f"[agentchaos] disabled | fired={len(engine.log)}, intercepts={engine._intercept_count}")
    return engine


def save_trace(path: str) -> None:
    """Save the last engine's trace to a JSON file. One line.

    Each entry contains raw_input (model, messages, tools), raw_output (content, tool_calls, usage), timing.
    Call after disable().
    """
    eng = _last_engine
    if eng is None:
        logger.error("[agentchaos] save_trace: no trace to save (call disable() first)")
        return
    calls = []
    for entry in eng.trace:
        resp = entry.get("response", {})
        fault_applied = entry.get("fault", {}).get("applied", False)
        call_entry = {
            "call_index": entry.get("call_index", 0),
            "raw_input": {
                "model": entry.get("request", {}).get("model", ""),
                "messages": entry.get("request", {}).get("messages", []),
                "tools": entry.get("request", {}).get("tools", []),
            },
            "raw_output": {
                "content": resp.get("content", ""),
                "tool_calls": resp.get("tool_calls", []),
                "finish_reason": resp.get("finish_reason", ""),
                "usage": resp.get("usage", {}),
                "http_status": resp.get("http_status", 0),
            },
            "timing": entry.get("timing", {}),
            "fault_applied": fault_applied,
        }
        if fault_applied:
            call_entry["injected_output"] = {
                "content": resp.get("modified_content", ""),
                "tool_calls": resp.get("modified_tool_calls", []),
            }
        calls.append(call_entry)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(calls, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"[agentchaos] trace saved: {path} ({len(calls)} LLM calls)")


# ══════════════════════════════════════════════════════════════════
# Batch robustness evaluation
# ══════════════════════════════════════════════════════════════════


@dataclass
class EvalResult:
    """Result of one fault experiment on one agent run."""

    fault: str
    result: str
    error: str
    passed: bool
    elapsed: float
    faults_fired: int
    diagnosis: dict
    fault_log: list


@dataclass
class EvalReport:
    """Aggregated robustness evaluation report."""

    total: int
    passed: int
    failed: int
    results: List[EvalResult]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    @property
    def vulnerable_to(self) -> List[str]:
        return [r.fault for r in self.results if not r.passed]

    def summary(self) -> str:
        vuln = ", ".join(self.vulnerable_to[:5]) or "none"
        return f"{self.passed}/{self.total} passed ({self.pass_rate:.0%}) | vulnerable to: {vuln}"


async def eval(
    agent_fn: Callable,
    query: str = "Write a Python function that checks if a number is prime.",
    faults: Union[str, List[str]] = "all",
    kwargs: dict = None,
    seed: int = 42,
    baseline: bool = True,
) -> EvalReport:
    """Evaluate agent robustness across multiple fault configurations.

    Args:
        agent_fn: async callable with signature (query: str, **kwargs) -> str
        query: task for the agent
        faults: "all" (65 configs) or a list of fault names
        kwargs: extra kwargs passed to agent_fn
        seed: random seed
        baseline: if True, also run without chaos first
    """
    kwargs = kwargs or {}
    if faults == "all":
        fault_names = fault_config.list_all()
    elif isinstance(faults, str):
        fault_names = [faults]
    else:
        fault_names = list(faults)

    results = []

    # baseline run (no chaos)
    if baseline:
        start = time.time()
        try:
            result_text = await agent_fn(query, **kwargs) or ""
            error = ""
        except Exception as e:
            result_text, error = "", f"{type(e).__name__}: {e}"
        results.append(
            EvalResult(
                fault="baseline",
                result=result_text,
                error=error,
                passed=bool(result_text and not error),
                elapsed=round(time.time() - start, 2),
                faults_fired=0,
                diagnosis={"fault_type": "none", "confidence": "high", "hint": ""},
                fault_log=[],
            )
        )
        logger.info(f"[eval] baseline: {'PASS' if results[-1].passed else 'FAIL'} ({results[-1].elapsed}s)")

    # chaos evaluation: one run per fault config
    for i, fname in enumerate(fault_names):
        start = time.time()
        result_text, error, fault_log = "", "", []
        faults_fired = 0
        try:
            inject(fname, seed=seed)
            result_text = await agent_fn(query, **kwargs) or ""
            eng = disable()
            fault_log = list(eng.log)
            faults_fired = len(eng.log)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            disable()

        diag = diagnose(result_text) if result_text else diagnose("")
        passed = bool(result_text and not error and diag["fault_type"] == "unknown")
        elapsed = round(time.time() - start, 2)

        results.append(
            EvalResult(
                fault=fname,
                result=result_text,
                error=error,
                passed=passed,
                elapsed=elapsed,
                faults_fired=faults_fired,
                diagnosis=diag,
                fault_log=fault_log,
            )
        )
        status = "PASS" if passed else "FAIL"
        logger.info(f"[eval] {i + 1}/{len(fault_names)} {fname}: {status} ({elapsed}s, fired={faults_fired})")

    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    report = EvalReport(total=total, passed=passed_count, failed=total - passed_count, results=results)
    logger.info(f"[eval] done: {report.summary()}")
    return report


# ══════════════════════════════════════════════════════════════════
# Convenience: fault catalog access
# ══════════════════════════════════════════════════════════════════

list_faults = fault_config.list_all
list_faults_by_category = fault_config.list_by_category
get_fault = fault_config.get

__version__ = "0.1.0"
__all__ = [
    "inject",
    "disable",  # core: one-line non-intrusive fault injection
    "save_trace",  # save trace to JSON file
    "eval",  # batch robustness evaluation
    "diagnose",  # fault diagnosis from agent output
    "list_faults",
    "get_fault",  # fault catalog access
    "FaultEngine",
    "FaultSpec",  # advanced: custom fault definition
    "EvalResult",
    "EvalReport",  # evaluation result types
]
