# agentchaos/fault_engine.py — Fault injection engine (httpx-level monkey-patch)
# Intercepts any OpenAI-compatible API call via httpx, applies fault specs.
# Works with: openai SDK, litellm, langchain, autogen, crewai, etc.
import asyncio
import contextvars
import copy
import json
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, List, Tuple

import httpx
from loguru import logger


# ── JSON path helpers (minimal jp_get/jp_set) ──────────────────
def _parse_tokens(path: str) -> List:
    """Parse '$.choices[0].message.content' into ['choices', 0, 'message', 'content']."""
    if path in ("$", ""):
        return []
    tokens = []
    for part in path.lstrip("$.").split("."):
        m = re.match(r"^(\w+)\[(\d+)\]$", part)
        if m:
            tokens += [m.group(1), int(m.group(2))]
        elif part.isdigit():
            tokens.append(int(part))
        else:
            tokens.append(part)
    return tokens


def jp_get(data: Any, path: str) -> Any:
    """Get value at JSON path. Returns None if path doesn't exist."""
    try:
        cur = data
        for tok in _parse_tokens(path):
            cur = cur[tok]
        return cur
    except (KeyError, IndexError, TypeError):
        return None


def jp_set(data: Any, path: str, value: Any) -> Any:
    """Set value at JSON path. Modifies data in-place."""
    tokens = _parse_tokens(path)
    if not tokens:
        return value
    try:
        cur = data
        for tok in tokens[:-1]:
            cur = cur[tok]
        cur[tokens[-1]] = value
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"[jp_set] path={path} unreachable: {e}")
    return data


# ── FaultSpec: one fault rule ──────────────────────────────────
@dataclass
class FaultSpec:
    intercept: str  # "response" or "request"
    action: str  # "set", "corrupt", "truncate", "error", "delay", "drop", "duplicate"
    target_path: str = "$"
    value: Any = None
    max_count: int = 0  # 0 = unlimited
    min_count: int = 0  # skip first N fires
    probability: float = 1.0
    description: str = ""
    skip_guard: bool = False
    _count: int = field(default=0, repr=False)


# ── FaultEngine: manages multiple fault specs ──────────────────
class FaultEngine:
    """Core engine: holds FaultSpecs, applies them to intercepted requests/responses."""

    def __init__(self, seed: int = 42, trace_only: bool = False):
        self._faults: List[FaultSpec] = []
        self._rng = random.Random(seed)
        self._lock = threading.Lock()
        self.log: List[dict] = []  # fired fault events
        self.trace: List[dict] = []  # full per-LLM-call execution trace
        self.trace_only: bool = trace_only  # True = record only, no fault injection
        self._last_response: dict = {}  # for "duplicate" action
        self._intercept_count: int = 0
        self.max_intercepts: int = 100  # safety limit to prevent infinite loops

    def add(self, spec: FaultSpec) -> int:
        """Register a fault spec. Returns its index."""
        idx = len(self._faults)
        self._faults.append(spec)
        logger.info(
            f"[FaultEngine] added #{idx}: {spec.action}@{spec.intercept} prob={spec.probability} | {spec.description}"
        )
        return idx

    def clear(self):
        self._faults.clear()
        self.log.clear()
        self.trace.clear()

    def has_active_faults(self) -> bool:
        """True if any spec can still fire, or if trace_only mode is on."""
        if self.trace_only:
            return True  # always intercept to record trace, even with no faults
        return any(s.max_count <= 0 or s._count < s.max_count for s in self._faults)

    def _try_fire(self, spec: FaultSpec, intercept: str) -> bool:
        """Atomic check: should this spec fire now? Thread-safe."""
        with self._lock:
            if spec.max_count > 0 and spec._count >= spec.max_count:
                return False
            if spec.probability < 1.0 and self._rng.random() > spec.probability:
                return False
            spec._count += 1
            # delayed onset: count but don't fire until min_count reached
            if spec.min_count > 0 and spec._count <= spec.min_count:
                return False
            self.log.append({"t": time.time(), "action": spec.action, "desc": spec.description, "count": spec._count})
        logger.info(f"[FaultEngine] FIRED: {spec.action}@{intercept} #{spec._count} | {spec.description}")
        return True

    def _corrupt_unicode(self, text: str) -> str:
        """Replace ~20% of chars with random Unicode symbols."""
        chars = list(text)
        with self._lock:
            for _ in range(max(1, len(chars) // 5)):
                i = self._rng.randint(0, len(chars) - 1)
                chars[i] = chr(self._rng.randint(0x2600, 0x26FF))
        return "".join(chars)

    def _truncate_json_values(self, json_str: str, ratio: float) -> str:
        """Truncate string values inside a JSON string (for tool_calls arguments)."""
        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return '{"_fault_truncated": true}'

        def _trunc(obj):
            if isinstance(obj, str):
                return obj[: max(1, int(len(obj) * ratio))]
            elif isinstance(obj, dict):
                return {k: _trunc(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_trunc(v) for v in obj]
            return obj

        return json.dumps(_trunc(data), ensure_ascii=False)

    def _corrupt_json_values(self, json_str: str) -> str:
        """Corrupt string values inside a JSON string."""
        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return '{"_fault_corrupted": true}'

        def _corrupt(obj):
            if isinstance(obj, str):
                return self._corrupt_unicode(obj)
            elif isinstance(obj, dict):
                return {k: _corrupt(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_corrupt(v) for v in obj]
            return obj

        return json.dumps(_corrupt(data), ensure_ascii=False)

    @staticmethod
    def _is_tool_arguments_path(path: str) -> bool:
        return "function.arguments" in path

    def apply(self, intercept: str, data: dict) -> Tuple[str, Any, float]:
        """Apply all matching fault specs. Returns (action, modified_data, delay_ms)."""
        result_data, result_action, delay_ms, copied = data, "pass", 0.0, False

        for spec in self._faults:
            if spec.intercept != intercept:
                continue

            # guard: skip content faults when tool_calls present (and vice versa)
            if not spec.skip_guard and spec.target_path.startswith("$.choices[0].message.content"):
                tc = jp_get(result_data, "$.choices[0].message.tool_calls")
                if isinstance(tc, list) and len(tc) > 0:
                    continue
            if not spec.skip_guard and spec.target_path.startswith("$.choices[0].message.tool_calls"):
                tc = jp_get(result_data, "$.choices[0].message.tool_calls")
                if not isinstance(tc, list) or len(tc) == 0:
                    continue

            if not self._try_fire(spec, intercept):
                continue

            # deep copy before first mutation
            if not copied and spec.action in ("set", "corrupt", "truncate"):
                result_data = copy.deepcopy(result_data)
                copied = True

            if spec.action == "set":
                result_data = jp_set(result_data, spec.target_path, spec.value)
                result_action = "modify"

            elif spec.action == "corrupt":
                orig = jp_get(result_data, spec.target_path)
                if isinstance(orig, str) and orig:
                    if self._is_tool_arguments_path(spec.target_path):
                        jp_set(result_data, spec.target_path, self._corrupt_json_values(orig))
                    else:
                        mode = spec.value if isinstance(spec.value, str) else "unicode"
                        if mode == "mojibake":
                            try:
                                corrupted = orig.encode("utf-8").decode("latin-1")
                            except (UnicodeDecodeError, UnicodeEncodeError):
                                corrupted = self._corrupt_unicode(orig)
                        elif mode == "broken_json":
                            corrupted = orig[: max(1, len(orig) // 2)] + "\x00\x00"
                        else:
                            corrupted = self._corrupt_unicode(orig)
                        jp_set(result_data, spec.target_path, corrupted)
                    result_action = "modify"

            elif spec.action == "truncate":
                orig = jp_get(result_data, spec.target_path)
                ratio = spec.value if isinstance(spec.value, (int, float)) and 0 < spec.value < 1 else 0.5
                if isinstance(orig, str) and orig:
                    if self._is_tool_arguments_path(spec.target_path):
                        jp_set(result_data, spec.target_path, self._truncate_json_values(orig, ratio))
                    else:
                        jp_set(result_data, spec.target_path, orig[: max(1, int(len(orig) * ratio))])
                        if "message.content" in spec.target_path:
                            jp_set(result_data, "$.choices[0].finish_reason", "length")
                    result_action = "modify"
                elif isinstance(orig, list) and orig:
                    jp_set(result_data, spec.target_path, orig[: max(1, int(len(orig) * ratio))])
                    result_action = "modify"

            elif spec.action == "error":
                code = spec.value if isinstance(spec.value, int) else 500
                if not copied:
                    result_data = copy.deepcopy(result_data)
                    copied = True
                jp_set(
                    result_data,
                    "$.choices[0].message.content",
                    f"[API ERROR] HTTP {code}: AgentFault injected server error.",
                )
                result_action = "modify"

            elif spec.action == "delay":
                ms = spec.value if isinstance(spec.value, (int, float)) else 2000
                delay_ms += ms
                if result_action == "pass":
                    result_action = "delay"

            elif spec.action == "drop":
                if not copied:
                    result_data = copy.deepcopy(result_data)
                    copied = True
                jp_set(
                    result_data,
                    "$.choices[0].message.content",
                    "[TIMEOUT] Connection dropped. The server did not respond.",
                )
                jp_set(result_data, "$.choices[0].message.tool_calls", [])
                result_action = "modify"

            elif spec.action == "duplicate":
                with self._lock:
                    cached = copy.deepcopy(self._last_response) if self._last_response else None
                if cached is not None:
                    result_data = cached
                    result_action = "modify"

        return result_action, result_data, delay_ms


# ── httpx monkey-patch (global, per-coroutine engine via contextvars) ──
_current_engine: contextvars.ContextVar = contextvars.ContextVar("_current_engine", default=None)
_original_async_send = httpx.AsyncClient.send
_patch_installed = False


def _install_global_patch():
    """Patch httpx.AsyncClient.send once. Routes to per-coroutine FaultEngine."""
    global _patch_installed
    if _patch_installed:
        return

    async def _patched_send(self, request: httpx.Request, *, stream=False, **kwargs):
        url = str(request.url)
        # only intercept OpenAI-compatible chat completions
        if "/chat/completions" not in url:
            return await _original_async_send(self, request, stream=stream, **kwargs)

        engine = _current_engine.get()
        if engine is None or not engine.has_active_faults():
            return await _original_async_send(self, request, stream=stream, **kwargs)

        # safety limit: prevent infinite retry loops
        with engine._lock:
            engine._intercept_count += 1
            ic = engine._intercept_count
        if ic > engine.max_intercepts:
            raise httpx.ReadTimeout(f"AgentChaos: safety limit ({engine.max_intercepts} intercepts)", request=request)

        try:
            req_body = json.loads(request.content)
        except (json.JSONDecodeError, TypeError):
            return await _original_async_send(self, request, stream=stream, **kwargs)

        logger.info(f"[httpx] intercepted {url} | model={req_body.get('model', '?')}")

        # -- trace: record request info --
        call_start = time.time()
        trace_entry = {
            "call_index": len(engine.trace),
            "timestamp": call_start,
            "request": {
                "model": req_body.get("model", "unknown"),
                "messages": req_body.get("messages", []),
                "tools": [t.get("function", {}).get("name", "?") for t in req_body.get("tools", [])],
            },
            "response": {},
            "timing": {},
            "fault": {"request_action": "pass", "response_action": "pass", "delay_ms": 0},
        }

        # request-side faults
        req_action, req_body, req_delay = engine.apply("request", req_body)
        trace_entry["fault"]["request_action"] = req_action
        if req_delay > 0:
            trace_entry["fault"]["delay_ms"] += req_delay
            await asyncio.sleep(req_delay / 1000.0)

        # force non-streaming (can't fault-inject SSE streams)
        if req_body.get("stream", False) or stream:
            req_body["stream"] = False
            stream = False
            if req_action == "pass":
                req_action = "modify"

        # rebuild request if modified
        if req_action in ("modify", "delay"):
            new_bytes = json.dumps(req_body).encode("utf-8")
            headers = dict(request.headers)
            headers["content-length"] = str(len(new_bytes))
            request = httpx.Request(method=request.method, url=request.url, headers=headers, content=new_bytes)

        # send real request
        llm_start = time.time()
        response = await _original_async_send(self, request, stream=stream, **kwargs)
        if not response.is_stream_consumed:
            await response.aread()
        llm_end = time.time()
        trace_entry["timing"]["llm_latency_ms"] = round((llm_end - llm_start) * 1000, 1)
        trace_entry["response"]["http_status"] = response.status_code

        # response-side faults
        try:
            resp_body = response.json()
        except (json.JSONDecodeError, TypeError):
            # -- trace: record even on parse failure --
            trace_entry["response"]["parse_error"] = "failed to parse response JSON"
            trace_entry["timing"]["total_ms"] = round((time.time() - call_start) * 1000, 1)
            engine.trace.append(trace_entry)
            return response

        # -- trace: record original response before fault injection --
        _orig_msg = jp_get(resp_body, "$.choices[0].message") or {}
        trace_entry["response"]["content"] = _orig_msg.get("content", "")
        trace_entry["response"]["tool_calls"] = [
            {"name": tc.get("function", {}).get("name", "?"), "arguments": tc.get("function", {}).get("arguments", "")}
            for tc in (_orig_msg.get("tool_calls") or [])
        ]
        trace_entry["response"]["finish_reason"] = jp_get(resp_body, "$.choices[0].finish_reason")
        # token usage from the LLM API
        _usage = resp_body.get("usage") or {}
        trace_entry["response"]["usage"] = {
            "prompt_tokens": _usage.get("prompt_tokens", 0),
            "completion_tokens": _usage.get("completion_tokens", 0),
            "total_tokens": _usage.get("total_tokens", 0),
        }

        resp_action, resp_body, resp_delay = engine.apply("response", resp_body)
        trace_entry["fault"]["response_action"] = resp_action
        # cache for "duplicate" replay
        if isinstance(resp_body, dict):
            with engine._lock:
                engine._last_response = copy.deepcopy(resp_body)
        if resp_delay > 0:
            trace_entry["fault"]["delay_ms"] += resp_delay
            await asyncio.sleep(resp_delay / 1000.0)

        # -- trace: record modified response if fault applied --
        if resp_action not in ("pass", "delay"):
            _mod_msg = jp_get(resp_body, "$.choices[0].message") or {}
            trace_entry["response"]["modified_content"] = _mod_msg.get("content", "")
            trace_entry["response"]["modified_tool_calls"] = [
                {
                    "name": tc.get("function", {}).get("name", "?"),
                    "arguments": tc.get("function", {}).get("arguments", ""),
                }
                for tc in (_mod_msg.get("tool_calls") or [])
            ]

        # -- trace: finalize timing and append --
        trace_entry["timing"]["total_ms"] = round((time.time() - call_start) * 1000, 1)
        trace_entry["fault"]["applied"] = resp_action not in ("pass", "delay") or req_action not in ("pass",)
        engine.trace.append(trace_entry)
        logger.debug(
            f"[trace] call #{trace_entry['call_index']} "
            f"model={trace_entry['request']['model']} "
            f"total={trace_entry['timing']['total_ms']}ms "
            f"fault={trace_entry['fault']['applied']}"
        )

        if resp_action in ("pass", "delay"):
            return response

        # return modified response
        new_bytes = json.dumps(resp_body).encode("utf-8")
        return httpx.Response(
            response.status_code, content=new_bytes, headers={"content-type": "application/json"}, request=request
        )

    httpx.AsyncClient.send = _patched_send
    _patch_installed = True
    logger.info("[httpx] global patch installed")


def install(engine: FaultEngine):
    """Install fault engine for current coroutine."""
    _install_global_patch()
    _current_engine.set(engine)


def uninstall():
    """Remove fault engine from current coroutine."""
    _current_engine.set(None)
