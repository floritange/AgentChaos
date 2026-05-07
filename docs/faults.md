# Fault Reference

Complete reference for all 65 fault configurations in AgentChaos.

## Quick Reference

| ID | Target | Type | Strategy | Real-world Scenario |
|---|---|---|---|---|
| `llm_error_single` | Content | Crash/Error | Single | HTTP 5xx, rate limiting |
| `llm_error_persistent` | Content | Crash/Error | Persistent | API key expired, region outage |
| `llm_error_intermittent` | Content | Crash/Error | Intermittent | Flaky connection |
| `llm_error_burst` | Content | Crash/Error | Burst | Rate limit burst |
| `llm_timeout_single` | Content | Crash/Timeout | Single | Network glitch |
| `llm_timeout_persistent` | Content | Crash/Timeout | Persistent | Backend delay |
| `llm_timeout_intermittent` | Content | Crash/Timeout | Intermittent | Packet loss |
| `llm_timeout_burst` | Content | Crash/Timeout | Burst | Congestion burst |
| `llm_empty_single` | Content | Omission/Empty | Single | Safety filter |
| `llm_empty_persistent` | Content | Omission/Empty | Persistent | Content policy block |
| `llm_empty_intermittent` | Content | Omission/Empty | Intermittent | Intermittent filter |
| `llm_empty_burst` | Content | Omission/Empty | Burst | Capacity exhaustion |
| `llm_truncate_single` | Content | Omission/Truncate | Single | Token limit |
| `llm_truncate_persistent` | Content | Omission/Truncate | Persistent | TCP disconnect |
| `llm_truncate_intermittent` | Content | Omission/Truncate | Intermittent | Streaming interruption |
| `llm_truncate_burst` | Content | Omission/Truncate | Burst | Burst truncation |
| `llm_corrupt_single` | Content | Value/Corrupt | Single | Encoding error |
| `llm_corrupt_persistent` | Content | Value/Corrupt | Persistent | Proxy charset mismatch |
| `llm_corrupt_intermittent` | Content | Value/Corrupt | Intermittent | Intermittent corruption |
| `llm_corrupt_burst` | Content | Value/Corrupt | Burst | Cache corruption burst |
| `llm_schema_single` | Content | Value/Schema | Single | Parsing error |
| `llm_schema_persistent` | Content | Value/Schema | Persistent | Schema mismatch |
| `llm_schema_intermittent` | Content | Value/Schema | Intermittent | Malformed output |
| `llm_schema_burst` | Content | Value/Schema | Burst | API version mismatch |
| `tool_error_single` | Tool call | Crash/Error | Single | Missing required params |
| `tool_error_persistent` | Tool call | Crash/Error | Persistent | Persistent tool failure |
| `tool_error_intermittent` | Tool call | Crash/Error | Intermittent | Flaky tool |
| `tool_error_burst` | Tool call | Crash/Error | Burst | Tool burst failure |
| `tool_timeout_single` | Tool call | Crash/Timeout | Single | Tool never executed |
| `tool_timeout_persistent` | Tool call | Crash/Timeout | Persistent | Persistent drop |
| `tool_timeout_intermittent` | Tool call | Crash/Timeout | Intermittent | Intermittent drop |
| `tool_timeout_burst` | Tool call | Crash/Timeout | Burst | Burst drop |
| `tool_empty_single` | Tool call | Omission/Empty | Single | Tool calls stripped |
| `tool_empty_persistent` | Tool call | Omission/Empty | Persistent | No tool invocation |
| `tool_empty_intermittent` | Tool call | Omission/Empty | Intermittent | Intermittent strip |
| `tool_empty_burst` | Tool call | Omission/Empty | Burst | Burst strip |
| `tool_truncate_single` | Tool call | Omission/Truncate | Single | Broken JSON arguments |
| `tool_truncate_persistent` | Tool call | Omission/Truncate | Persistent | Persistent truncation |
| `tool_truncate_intermittent` | Tool call | Omission/Truncate | Intermittent | Intermittent truncation |
| `tool_truncate_burst` | Tool call | Omission/Truncate | Burst | Burst truncation |
| `tool_corrupt_single` | Tool call | Value/Corrupt | Single | Garbled params |
| `tool_corrupt_persistent` | Tool call | Value/Corrupt | Persistent | Persistent garble |
| `tool_corrupt_intermittent` | Tool call | Value/Corrupt | Intermittent | Intermittent garble |
| `tool_corrupt_burst` | Tool call | Value/Corrupt | Burst | Burst garble |
| `tool_schema_single` | Tool call | Value/Schema | Single | Wrong param keys |
| `tool_schema_persistent` | Tool call | Value/Schema | Persistent | Persistent wrong schema |
| `tool_schema_intermittent` | Tool call | Value/Schema | Intermittent | Intermittent wrong schema |
| `tool_schema_burst` | Tool call | Value/Schema | Burst | Burst wrong schema |
| `compound_api_degradation` | Content | Compound | — | 3s delay + HTTP 503 |
| `compound_content_filter` | Both | Compound | — | Strip tool_calls + filter message |
| `compound_max_tokens` | Content | Compound | — | Truncate 50% + finish_reason=length |
| `compound_proxy_html` | Content | Compound | — | nginx 502 HTML page |
| `compound_stale_cache` | Content | Compound | — | CDN replays previous response |
| `compound_stale_data` | Tool call | Compound | — | Wrong tool argument (hallucination) |
| `compound_wrong_entity` | Tool call | Compound | — | Ambiguous entity argument |
| `compound_slow_response` | Content | Compound | — | 5s delay, eventually succeeds |
| `llm_error_pos_early` | Content | Positional | 1st call | Error at planning stage |
| `llm_error_pos_mid` | Content | Positional | 2nd call | Error at tool delegation |
| `llm_error_pos_late` | Content | Positional | 3rd call | Error at summary stage |
| `llm_timeout_pos_early` | Content | Positional | 1st call | Timeout at planning stage |
| `llm_timeout_pos_mid` | Content | Positional | 2nd call | Timeout at tool delegation |
| `llm_timeout_pos_late` | Content | Positional | 3rd call | Timeout at summary stage |
| `llm_schema_pos_early` | Content | Positional | 1st call | Schema fault at planning stage |
| `llm_schema_pos_mid` | Content | Positional | 2nd call | Schema fault at tool delegation |
| `llm_schema_pos_late` | Content | Positional | 3rd call | Schema fault at summary stage |

---

## Faults by Category

### Crash Faults

Crash faults make the response completely unusable. The receiving agent gets no valid information.

- **Error**: LLM API returns an error message instead of expected output. Happens during server overload, deployment rollouts, or rate limiting.
- **Timeout**: LLM API does not respond within the allowed time. Happens during network congestion or backend processing delays.

### Omission Faults

Omission faults return a valid response structure with missing or incomplete content.

- **Empty**: LLM API returns a response with no content. Happens when a safety filter or content policy blocks the output.
- **Truncate**: LLM API returns a response cut off partway through. Happens when the token limit is reached or a TCP connection drops. The agent receives a partial response that looks like a short but complete answer — making truncation harder to detect than an empty response.

### Value Faults

Value faults return a structurally valid and complete response with wrong content. These are the **hardest to detect** because the response looks normal.

- **Corrupt**: Response content is damaged by encoding errors (UTF-8 → Latin-1 misinterpretation). For tool calls, ~20% of characters are replaced with random Unicode symbols.
- **Schema**: Response contains valid JSON that does not follow the expected structure. No parsing error is raised, and the fault propagates silently.

---

## Target Fields

| Target | JSON Path | Description |
|---|---|---|
| Content | `$.choices[0].message.content` | Generated text that the next agent reads |
| Tool call | `$.choices[0].message.tool_calls[0].function.arguments` | Structured JSON arguments passed to tools |

Faults on `content` corrupt text. Faults on `tool_calls` corrupt tool arguments. Because `content` is plain text while `tool_calls` contains structured JSON, the same fault type affects each field differently.

---

## Injection Strategies

| Strategy | `max_count` | `probability` | Simulates |
|---|---|---|---|
| **Single** | 1 | 1.0 | Transient network glitch |
| **Persistent** | unlimited | 1.0 | API key expired, region outage |
| **Intermittent** | unlimited | 0.3 | Flaky connection (~30% packet loss) |
| **Burst** | 3 | 1.0 | Rate limit burst, then recover |

---

## Compound Faults

Compound faults combine multiple fault specs to simulate realistic multi-step failure scenarios.

| ID | Description |
|---|---|
| `compound_api_degradation` | 3s latency spike, then HTTP 503 error |
| `compound_content_filter` | Strip tool_calls + replace content with filter message + set finish_reason=content_filter |
| `compound_max_tokens` | Truncate content at 50% + set finish_reason=length |
| `compound_proxy_html` | Content replaced with nginx 502 HTML error page |
| `compound_stale_cache` | CDN replays stale cached response (fires on 2nd call) |
| `compound_stale_data` | Tool arguments set to wrong value (semantic hallucination) |
| `compound_wrong_entity` | Tool arguments set to ambiguous entity name |
| `compound_slow_response` | 5s delay, response eventually succeeds |

---

## Positional Faults

Positional faults inject at a specific LLM call index to test position-sensitivity.

| Position | Fires at | Typical agent stage |
|---|---|---|
| `early` | 1st LLM call | Planning / first generation |
| `mid` | 2nd LLM call | Tool delegation / refinement |
| `late` | 3rd LLM call | Post-tool summary / final answer |

**Key finding**: Early-stage faults in pipeline architectures are most devastating — a single fault at the planner drops Δpass@1 by up to 83.87%.

---

## Custom Fault Definition

```python
from agentchaos import FaultEngine, FaultSpec, inject, disable, save_trace

engine = FaultEngine(seed=42)
engine.add(FaultSpec(
    intercept="response",
    action="truncate",
    target_path="$.choices[0].message.content",
    value=0.5,           # truncate at 50%
    max_count=2,         # fire twice
    probability=0.8,     # 80% chance each time
    description="Custom: heavy truncation",
))

from agentchaos.fault_engine import install, uninstall
install(engine)
result = await my_agent(query)
uninstall()

print(engine.log)    # what faults fired
print(engine.trace)  # full LLM call records
```

### FaultSpec Fields

| Field | Type | Description |
|---|---|---|
| `intercept` | `"response"` or `"request"` | Which side to intercept |
| `action` | str | `set`, `corrupt`, `truncate`, `error`, `delay`, `drop`, `duplicate` |
| `target_path` | str | JSON path (e.g. `$.choices[0].message.content`) |
| `value` | any | Action-specific value (error code, truncation ratio, delay ms) |
| `max_count` | int | Max fires (0 = unlimited) |
| `min_count` | int | Skip first N fires (delayed onset) |
| `probability` | float | Fire probability per intercept (0.0–1.0) |
| `skip_guard` | bool | Skip content/tool_calls mutual exclusion guard |
