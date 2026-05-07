# examples/agent_langchain.py — LangChain agent: normal vs fault injection
#
# Usage:  uv run --extra research python examples/agent_langchain.py
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import agentchaos  # noqa: E402

FAULT = "llm_empty_single"
QUERY = "What is the square root of 144?"
TRACE_DIR = str(Path(__file__).resolve().parent / "traces")


# ── Agent (zero agentchaos knowledge) ────────────────────────────


async def agent(query: str) -> str:
    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI

    @tool
    def calculator(expression: str) -> str:
        """Evaluate a math expression."""
        try:
            return str(eval(expression))
        except Exception as e:
            return f"Error: {e}"

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        max_retries=0,
    )
    llm_with_tools = llm.bind_tools([calculator])

    messages = [HumanMessage(content=query)]
    for _ in range(5):
        resp = await llm_with_tools.ainvoke(messages)
        messages.append(resp)
        if not resp.tool_calls:
            return resp.content or ""
        for tc in resp.tool_calls:
            try:
                result = calculator.invoke(tc["args"])
            except Exception as e:
                result = f"Error: {e}"
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
    return messages[-1].content if hasattr(messages[-1], "content") else ""


# ── Run: normal vs faulted ───────────────────────────────────────


async def main():
    # 1. Normal run (trace only)
    print(f"{'=' * 60}\n[Normal] query: {QUERY}\n{'=' * 60}")
    agentchaos.inject(None)
    result = await agent(QUERY)
    agentchaos.disable()
    agentchaos.save_trace(f"{TRACE_DIR}/trace_langchain_normal.json")
    print(f"  Result: {result}")

    # 2. Faulted run (inject fault + trace)
    print(f"\n{'=' * 60}\n[Faulted: {FAULT}] query: {QUERY}\n{'=' * 60}")
    agentchaos.inject(FAULT)
    result_f = await agent(QUERY)
    agentchaos.disable()
    agentchaos.save_trace(f"{TRACE_DIR}/trace_langchain_faulted.json")
    print(f"  Result: {result_f or '(empty)'}")
    print(f"  Diagnosis: {agentchaos.diagnose(result_f or '')}")


if __name__ == "__main__":
    asyncio.run(main())
