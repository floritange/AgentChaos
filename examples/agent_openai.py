# examples/agent_openai.py — OpenAI SDK agent: normal vs fault injection
#
# Usage:  uv run python examples/agent_openai.py
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import agentchaos  # noqa: E402

FAULT = "llm_error_single"
QUERY = "What is 17 * 23 + 42?"
TRACE_DIR = str(Path(__file__).resolve().parent / "traces")


# ── Agent (zero agentchaos knowledge) ────────────────────────────


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


# ── Run: normal vs faulted ───────────────────────────────────────


async def main():
    # 1. Normal run (trace only)
    print(f"{'=' * 60}\n[Normal] query: {QUERY}\n{'=' * 60}")
    agentchaos.inject(None)
    result = await agent(QUERY)
    agentchaos.disable()
    agentchaos.save_trace(f"{TRACE_DIR}/trace_openai_normal.json")
    print(f"  Result: {result}")

    # 2. Faulted run (inject fault + trace)
    print(f"\n{'=' * 60}\n[Faulted: {FAULT}] query: {QUERY}\n{'=' * 60}")
    agentchaos.inject(FAULT)
    result_f = await agent(QUERY)
    agentchaos.disable()
    agentchaos.save_trace(f"{TRACE_DIR}/trace_openai_faulted.json")
    print(f"  Result: {result_f or '(empty)'}")
    print(f"  Diagnosis: {agentchaos.diagnose(result_f or '')}")


if __name__ == "__main__":
    asyncio.run(main())
