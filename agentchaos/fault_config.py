# agentchaos/fault_config.py — 65 pre-built fault experiments
# 6 fault types × 2 targets × 4 strategies + 8 compound + 9 positional
import copy
import sys

from loguru import logger

from .fault_engine import FaultSpec

# ── 4 injection strategies (how often a fault fires) ───────────
STRATEGIES = {
    "single": {"max_count": 1, "probability": 1.0},  # one-time glitch
    "persistent": {"max_count": sys.maxsize, "probability": 1.0},  # every call fails
    "intermittent": {"max_count": sys.maxsize, "probability": 0.3},  # 30% random failure
    "burst": {"max_count": 3, "probability": 1.0},  # 3 failures then recover
}

# ── 6 LLM response fault types ────────────────────────────────
LLM_FAULT_BASES = [
    (
        "llm_error",
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.content",
            value="[API ERROR] HTTP 500: Internal Server Error. The server encountered an unexpected condition.",
            description="LLM returns error message in content (server overloaded)",
        ),
    ),
    (
        "llm_timeout",
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.content",
            value="[TIMEOUT] The request timed out. The server did not respond within the expected time.",
            description="LLM returns timeout message (server unresponsive)",
        ),
    ),
    (
        "llm_empty",
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.content",
            value="",
            description="LLM returns empty content (safety filter / capacity limit)",
        ),
    ),
    (
        "llm_truncate",
        FaultSpec(
            intercept="response",
            action="truncate",
            target_path="$.choices[0].message.content",
            value=0.3,
            description="LLM content truncated at 30% (max_tokens / TCP disconnect)",
        ),
    ),
    (
        "llm_corrupt",
        FaultSpec(
            intercept="response",
            action="corrupt",
            target_path="$.choices[0].message.content",
            value="mojibake",
            description="LLM output encoding corruption (proxy charset mismatch)",
        ),
    ),
    (
        "llm_schema",
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.content",
            value='{"error": "content_policy_violation", "message": "This response has been filtered."}',
            description="LLM returns JSON-like string instead of natural language (structural anomaly)",
        ),
    ),
]

# ── 6 tool call fault types ───────────────────────────────────
TOOL_FAULT_BASES = [
    (
        "tool_error",
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.tool_calls[0].function.arguments",
            value="{}",
            description="LLM returns empty tool arguments (missing required params)",
        ),
    ),
    (
        "tool_timeout",
        FaultSpec(
            intercept="response",
            action="drop",
            target_path="$.choices[0].message.tool_calls[0]",
            description="LLM response lost when tool_calls present (tool never executed)",
        ),
    ),
    (
        "tool_empty",
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.tool_calls",
            value=[],
            description="LLM tool_calls stripped (tool never invoked)",
        ),
    ),
    (
        "tool_truncate",
        FaultSpec(
            intercept="response",
            action="truncate",
            target_path="$.choices[0].message.tool_calls[0].function.arguments",
            value=0.3,
            description="Tool call arguments truncated at 30% (broken JSON)",
        ),
    ),
    (
        "tool_corrupt",
        FaultSpec(
            intercept="response",
            action="corrupt",
            target_path="$.choices[0].message.tool_calls[0].function.arguments",
            value="unicode",
            description="Tool call arguments corrupted (garbled params)",
        ),
    ),
    (
        "tool_schema",
        FaultSpec(
            intercept="response",
            action="set",
            target_path="$.choices[0].message.tool_calls[0].function.arguments",
            value='{"wrong_param": "unexpected_value"}',
            description="Tool call arguments wrong schema (unexpected param keys)",
        ),
    ),
]

# ── 8 compound / realistic scenarios ──────────────────────────
COMPOUND_BASES = [
    (
        "compound_api_degradation",
        [
            FaultSpec(
                intercept="response",
                action="delay",
                value=3000,
                max_count=1,
                description="3s latency spike (service under load)",
            ),
            FaultSpec(
                intercept="response",
                action="set",
                target_path="$.choices[0].message.content",
                value="[SERVICE UNAVAILABLE] HTTP 503: The server is temporarily unable to handle the request.",
                max_count=1,
                description="Error after delay (service degraded)",
            ),
        ],
    ),
    (
        "compound_content_filter",
        [
            FaultSpec(
                intercept="response",
                action="set",
                target_path="$.choices[0].message.tool_calls",
                value=[],
                max_count=1,
                description="tool_calls stripped (safety filter)",
            ),
            FaultSpec(
                intercept="response",
                action="set",
                target_path="$.choices[0].message.content",
                value="[CONTENT FILTERED] This response has been blocked by the content safety filter.",
                max_count=1,
                description="content replaced with filter message",
            ),
            FaultSpec(
                intercept="response",
                action="set",
                target_path="$.choices[0].finish_reason",
                value="content_filter",
                max_count=1,
                description="finish_reason=content_filter",
            ),
        ],
    ),
    (
        "compound_max_tokens",
        [
            FaultSpec(
                intercept="response",
                action="truncate",
                target_path="$.choices[0].message.content",
                value=0.5,
                max_count=1,
                description="content truncated at 50%",
            ),
            FaultSpec(
                intercept="response",
                action="set",
                target_path="$.choices[0].finish_reason",
                value="length",
                max_count=1,
                description="finish_reason=length",
            ),
        ],
    ),
    (
        "compound_proxy_html",
        [
            FaultSpec(
                intercept="response",
                action="set",
                target_path="$.choices[0].message.content",
                value=(
                    "<!DOCTYPE html>\n<html><head><title>502 Bad Gateway</title></head>\n"
                    "<body><center><h1>502 Bad Gateway</h1></center><hr>"
                    "<center>nginx/1.24.0</center></body></html>"
                ),
                max_count=1,
                description="HTML error page instead of normal text (proxy leak)",
            ),
        ],
    ),
    (
        "compound_stale_cache",
        [
            FaultSpec(
                intercept="response",
                action="duplicate",
                max_count=2,
                min_count=1,
                description="CDN replays stale cached response",
            ),
        ],
    ),
    (
        "compound_stale_data",
        [
            FaultSpec(
                intercept="response",
                action="set",
                target_path="$.choices[0].message.tool_calls[0].function.arguments",
                value='{"city": "Pyongyang"}',
                max_count=1,
                description="LLM hallucinates wrong tool argument",
            ),
        ],
    ),
    (
        "compound_wrong_entity",
        [
            FaultSpec(
                intercept="response",
                action="set",
                target_path="$.choices[0].message.tool_calls[0].function.arguments",
                value='{"city": "Springfield"}',
                max_count=1,
                description="LLM hallucinates ambiguous tool argument",
            ),
        ],
    ),
    (
        "compound_slow_response",
        [
            FaultSpec(
                intercept="response",
                action="delay",
                value=5000,
                max_count=1,
                description="5s response delay (server under load, succeeds)",
            ),
        ],
    ),
]


# ── Build full experiment list ─────────────────────────────────
def _build_experiments() -> list:
    experiments = []
    # (1) 6 types × 2 targets × 4 strategies = 48
    for bases, _label in [(LLM_FAULT_BASES, "llm"), (TOOL_FAULT_BASES, "tool")]:
        for base_name, base_spec in bases:
            for strat_name, strat_params in STRATEGIES.items():
                spec = copy.deepcopy(base_spec)
                spec.max_count = strat_params["max_count"]
                spec.probability = strat_params["probability"]
                spec.description = f"{base_spec.description} [{strat_name}]"
                experiments.append({"name": f"{base_name}_{strat_name}", "faults": [spec]})
    # (2) 8 compound scenarios
    for comp_name, comp_specs in COMPOUND_BASES:
        experiments.append({"name": comp_name, "faults": [copy.deepcopy(s) for s in comp_specs]})
    # (3) 3 faults × 3 positions = 9 positional experiments
    positions = {
        "early": {"min_count": 0, "max_count": 1},
        "mid": {"min_count": 1, "max_count": 2},
        "late": {"min_count": 2, "max_count": 3},
    }
    base_lookup = {n: s for n, s in LLM_FAULT_BASES + TOOL_FAULT_BASES}
    for fault_name in ["llm_error", "llm_timeout", "llm_schema"]:
        base_spec = base_lookup.get(fault_name)
        if not base_spec:
            continue
        for pos_name, pos_params in positions.items():
            spec = copy.deepcopy(base_spec)
            spec.max_count = pos_params["max_count"]
            spec.min_count = pos_params["min_count"]
            spec.skip_guard = True
            spec.probability = 1.0
            spec.description = f"{base_spec.description} [position={pos_name}]"
            experiments.append({"name": f"{fault_name}_pos_{pos_name}", "faults": [spec]})

    logger.info(f"[catalog] built {len(experiments)} experiments")
    return experiments


EXPERIMENTS = _build_experiments()
EXPERIMENT_INDEX = {exp["name"]: exp for exp in EXPERIMENTS}


def get(name: str) -> dict:
    """Look up experiment by name. Raises ValueError if not found."""
    if name not in EXPERIMENT_INDEX:
        raise ValueError(f"Unknown experiment: '{name}'. Available: {list(EXPERIMENT_INDEX.keys())[:10]}...")
    return EXPERIMENT_INDEX[name]


def list_all() -> list:
    """Return all experiment names."""
    return sorted(EXPERIMENT_INDEX.keys())


def list_by_category() -> dict:
    """Return experiments grouped by category for UI display."""
    cats = {"llm": [], "tool": [], "compound": []}
    for bases, cat in [(LLM_FAULT_BASES, "llm"), (TOOL_FAULT_BASES, "tool")]:
        for base_name, base_spec in bases:
            ftype = base_name.split("_", 1)[1] if "_" in base_name else base_name
            cats[cat].append(
                {
                    "base_name": base_name,
                    "type": ftype,
                    "description": base_spec.description,
                    "strategies": list(STRATEGIES.keys()),
                    "experiments": {s: f"{base_name}_{s}" for s in STRATEGIES},
                }
            )
    for comp_name, comp_specs in COMPOUND_BASES:
        cats["compound"].append(
            {
                "base_name": comp_name,
                "type": "compound",
                "description": " + ".join(s.description for s in comp_specs),
                "strategies": [],
                "experiments": {"default": comp_name},
            }
        )
    return cats
