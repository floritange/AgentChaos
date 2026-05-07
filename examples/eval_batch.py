# examples/eval_batch.py — Batch evaluation: test one agent against multiple faults
#
# Usage:
#   uv run python examples/eval_batch.py
#   uv run python examples/eval_batch.py --limit 3
#   uv run python examples/eval_batch.py --all
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import agentchaos  # noqa: E402

QUERY = "What is 17 * 23 + 42?"
TRACE_DIR = str(Path(__file__).resolve().parent / "traces")

# 6 representative faults (one per category)
DEFAULT_FAULTS = [
    "llm_error_single",
    "llm_empty_single",
    "llm_truncate_single",
    "llm_corrupt_single",
    "llm_timeout_single",
    "compound_content_filter",
]


# ── Agent ────────────────────────────────────────────────────────


async def agent(query: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=os.getenv("OPENAI_BASE_URL"), api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-5.5")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Evaluate a math expression",
                "parameters": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
        }
    ]
    messages = [{"role": "user", "content": query}]
    for _ in range(5):
        resp = await client.chat.completions.create(model=model, messages=messages, tools=tools)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or ""
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            try:
                result = str(eval(json.loads(tc.function.arguments).get("expression", "0")))
            except Exception as e:
                result = f"Error: {e}"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return ""


# ── Batch eval ───────────────────────────────────────────────────


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--all", action="store_true")
    args = p.parse_args()

    faults = (
        agentchaos.list_faults() if args.all else (DEFAULT_FAULTS[: args.limit] if args.limit > 0 else DEFAULT_FAULTS)
    )

    print(f"Evaluating agent against {len(faults)} faults | query: {QUERY}\n")

    # Baseline (trace only)
    agentchaos.inject(None)
    result = await agent(QUERY)
    agentchaos.disable()
    agentchaos.save_trace(f"{TRACE_DIR}/trace_eval_baseline.json")
    print(f"  [baseline] PASS | result: {result[:80]}")

    # Each fault
    for i, fname in enumerate(faults):
        agentchaos.inject(fname)
        try:
            result = await agent(QUERY) or ""
        except Exception:
            result = ""
        engine = agentchaos.disable()
        agentchaos.save_trace(f"{TRACE_DIR}/trace_eval_{fname}.json")

        diag = agentchaos.diagnose(result)
        passed = bool(result and diag["fault_type"] == "unknown")
        status = "PASS" if passed else "FAIL"
        print(f"  [{i + 1}/{len(faults)}] {status} | {fname} | fired={len(engine.log)} calls={len(engine.trace)}")

    print(f"\nAll traces saved to {TRACE_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
