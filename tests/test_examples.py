# tests/test_examples.py — Verify all example scripts run correctly with mocked LLM
#
# Each test mocks httpx transport to return standard OpenAI responses,
# then runs the example's main() function end-to-end.
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

# Add project root to path so examples can import agentchaos
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Mock responses ──────────────────────────────────────────────

MOCK_CONTENT_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "model": "gpt-5.5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "The answer is 433.", "tool_calls": None},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }
).encode("utf-8")

MOCK_TOOL_CALL_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-mock-tool",
        "object": "chat.completion",
        "model": "gpt-5.5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {"name": "calculate", "arguments": '{"expression": "17*23+42"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 150, "completion_tokens": 30, "total_tokens": 180},
    }
).encode("utf-8")

MOCK_WEATHER_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-mock-weather",
        "object": "chat.completion",
        "model": "gpt-5.5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "The weather in Beijing is 22C and sunny.",
                    "tool_calls": None,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 15, "total_tokens": 115},
    }
).encode("utf-8")

MOCK_SQRT_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-mock-sqrt",
        "object": "chat.completion",
        "model": "gpt-5.5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "The square root of 144 is 12.", "tool_calls": None},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 80, "completion_tokens": 10, "total_tokens": 90},
    }
).encode("utf-8")


_call_count = 0


def _make_mock_send_stateful():
    """Mock that returns tool_call on first request, content on second (simulates agent loop)."""

    async def mock_send(self, request, *, stream=False, **kwargs):
        # Determine response based on request content
        try:
            body = json.loads(request.content)
            messages = body.get("messages", [])
            tools = body.get("tools", [])

            # If there's a tool result in messages, return final answer
            has_tool_result = any(m.get("role") == "tool" or m.get("role") == "function" for m in messages)
            # ADK uses "parts" with "functionResponse"
            has_adk_tool_result = any(
                any(p.get("functionResponse") for p in m.get("parts", []))
                for m in messages
                if isinstance(m, dict) and "parts" in m
            )

            if has_tool_result or has_adk_tool_result:
                content = MOCK_CONTENT_RESPONSE
            elif tools:
                # Extract first tool name from request to return correct tool call
                tool_name = "calculate"
                if tools:
                    first_tool = tools[0]
                    if isinstance(first_tool, dict):
                        fn = first_tool.get("function", first_tool)
                        tool_name = fn.get("name", "calculate")

                # Build tool call response with correct function name and arguments
                args = '{"expression": "17*23+42"}'
                if tool_name == "get_weather":
                    args = '{"city": "Beijing"}'

                tool_resp = json.dumps(
                    {
                        "id": "chatcmpl-mock-tool",
                        "object": "chat.completion",
                        "model": "gpt-5.5",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_abc123",
                                            "type": "function",
                                            "function": {"name": tool_name, "arguments": args},
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                        "usage": {"prompt_tokens": 150, "completion_tokens": 30, "total_tokens": 180},
                    }
                ).encode("utf-8")
                content = tool_resp
            else:
                content = MOCK_CONTENT_RESPONSE
        except (json.JSONDecodeError, TypeError):
            content = MOCK_CONTENT_RESPONSE

        return httpx.Response(200, content=content, headers={"content-type": "application/json"}, request=request)

    return mock_send


def _make_simple_mock_send():
    """Mock that always returns content response."""

    async def mock_send(self, request, *, stream=False, **kwargs):
        return httpx.Response(
            200, content=MOCK_CONTENT_RESPONSE, headers={"content-type": "application/json"}, request=request
        )

    return mock_send


# ── Test: list_faults.py ────────────────────────────────────────


class TestListFaults:
    def test_list_faults_runs(self, capsys):
        """examples/list_faults.py prints 65 faults."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("list_faults", ROOT / "examples" / "list_faults.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        captured = capsys.readouterr()
        assert "65" in captured.out


# ── Test: agent_openai.py ───────────────────────────────────────


class TestAgentOpenAI:
    @pytest.mark.asyncio
    async def test_openai_agent_normal_and_faulted(self):
        """examples/agent_openai.py runs normal + faulted with mock LLM."""
        with patch("agentchaos.fault_engine._original_async_send", new=_make_mock_send_stateful()):
            # Import and run the example's main
            import importlib.util

            spec = importlib.util.spec_from_file_location("agent_openai", ROOT / "examples" / "agent_openai.py")
            mod = importlib.util.module_from_spec(spec)

            # Set env vars for the example
            os.environ.setdefault("OPENAI_API_KEY", "fake-key")
            os.environ.setdefault("OPENAI_MODEL", "gpt-5.5")

            spec.loader.exec_module(mod)
            await mod.main()

        # Verify traces were saved
        trace_dir = ROOT / "examples" / "traces"
        assert (trace_dir / "trace_openai_normal.json").exists()
        assert (trace_dir / "trace_openai_faulted.json").exists()


# ── Test: agent_langchain.py ────────────────────────────────────


class TestAgentLangChain:
    @pytest.mark.asyncio
    async def test_langchain_agent_normal_and_faulted(self):
        """examples/agent_langchain.py runs normal + faulted with mock LLM."""
        with patch("agentchaos.fault_engine._original_async_send", new=_make_mock_send_stateful()):
            import importlib.util

            spec = importlib.util.spec_from_file_location("agent_langchain", ROOT / "examples" / "agent_langchain.py")
            mod = importlib.util.module_from_spec(spec)

            os.environ.setdefault("OPENAI_API_KEY", "fake-key")
            os.environ.setdefault("OPENAI_MODEL", "gpt-5.5")

            spec.loader.exec_module(mod)
            await mod.main()

        trace_dir = ROOT / "examples" / "traces"
        assert (trace_dir / "trace_langchain_normal.json").exists()
        assert (trace_dir / "trace_langchain_faulted.json").exists()


# ── Test: agent_adk.py ──────────────────────────────────────────


class TestAgentADK:
    @pytest.mark.asyncio
    async def test_adk_agent_normal_and_faulted(self):
        """examples/agent_adk.py runs normal + faulted with mock LLM."""
        with patch("agentchaos.fault_engine._original_async_send", new=_make_mock_send_stateful()):
            import importlib.util

            spec = importlib.util.spec_from_file_location("agent_adk", ROOT / "examples" / "agent_adk.py")
            mod = importlib.util.module_from_spec(spec)

            os.environ.setdefault("OPENAI_API_KEY", "fake-key")
            os.environ.setdefault("OPENAI_MODEL", "gpt-5.5")

            spec.loader.exec_module(mod)
            await mod.main()

        trace_dir = ROOT / "examples" / "traces"
        assert (trace_dir / "trace_adk_normal.json").exists()
        assert (trace_dir / "trace_adk_faulted.json").exists()


# ── Test: eval_batch.py ─────────────────────────────────────────


class TestEvalBatch:
    @pytest.mark.asyncio
    async def test_eval_batch_runs(self):
        """examples/eval_batch.py runs with --limit 2."""
        with patch("agentchaos.fault_engine._original_async_send", new=_make_mock_send_stateful()):
            import importlib.util

            spec = importlib.util.spec_from_file_location("eval_batch", ROOT / "examples" / "eval_batch.py")
            mod = importlib.util.module_from_spec(spec)

            os.environ.setdefault("OPENAI_API_KEY", "fake-key")
            os.environ.setdefault("OPENAI_MODEL", "gpt-5.5")

            # Patch sys.argv for argparse
            with patch.object(sys, "argv", ["eval_batch.py", "--limit", "2"]):
                spec.loader.exec_module(mod)
                await mod.main()

        trace_dir = ROOT / "examples" / "traces"
        assert (trace_dir / "trace_eval_baseline.json").exists()
