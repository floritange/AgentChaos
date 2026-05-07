# examples/agent_adk.py — Google ADK agent: normal vs fault injection
#
# Usage:  uv run --extra research python examples/agent_adk.py
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import agentchaos  # noqa: E402

FAULT = "llm_corrupt_single"
QUERY = "What's the weather in Beijing?"
TRACE_DIR = str(Path(__file__).resolve().parent / "traces")


# ── Agent (zero agentchaos knowledge) ────────────────────────────


async def agent(query: str) -> str:
    from google.adk.agents import LlmAgent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    def get_weather(city: str) -> dict:
        """Get current weather for a city."""
        return {"Beijing": "22C sunny", "Tokyo": "18C cloudy"}.get(city, "20C unknown")

    model = LiteLlm(
        model=f"openai/{os.getenv('OPENAI_MODEL', 'gpt-5.5')}",
        api_base=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    agent_inst = LlmAgent(
        name="WeatherAgent",
        model=model,
        instruction="Use get_weather tool to answer. Be concise.",
        tools=[get_weather],
    )
    ss = InMemorySessionService()
    runner = Runner(agent=agent_inst, app_name="demo", session_service=ss)
    session = await ss.create_session(app_name="demo", user_id="u")

    final = ""
    async for ev in runner.run_async(
        user_id="u",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=query)]),
    ):
        if ev.is_final_response() and ev.content and ev.content.parts:
            final = ev.content.parts[0].text or ""
    return final


# ── Run: normal vs faulted ───────────────────────────────────────


async def main():
    # 1. Normal run (trace only)
    print(f"{'=' * 60}\n[Normal] query: {QUERY}\n{'=' * 60}")
    agentchaos.inject(None)
    result = await agent(QUERY)
    agentchaos.disable()
    agentchaos.save_trace(f"{TRACE_DIR}/trace_adk_normal.json")
    print(f"  Result: {result}")

    # 2. Faulted run (inject fault + trace)
    print(f"\n{'=' * 60}\n[Faulted: {FAULT}] query: {QUERY}\n{'=' * 60}")
    agentchaos.inject(FAULT)
    result_f = await agent(QUERY)
    agentchaos.disable()
    agentchaos.save_trace(f"{TRACE_DIR}/trace_adk_faulted.json")
    print(f"  Result: {result_f or '(empty)'}")
    print(f"  Diagnosis: {agentchaos.diagnose(result_f or '')}")


if __name__ == "__main__":
    asyncio.run(main())
