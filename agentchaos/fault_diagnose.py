# agentchaos/fault_diagnose.py — Rule-based fault diagnosis
# Given agent output text, detect what type of fault was injected.
import re

# ── Detection patterns (ordered: first match wins) ────────────
RULE_PATTERNS = [
    (re.compile(r"\[API ERROR\]", re.IGNORECASE), "error"),
    (re.compile(r"HTTP 500.*Internal Server Error", re.IGNORECASE), "error"),
    (re.compile(r"\[SERVICE UNAVAILABLE\]", re.IGNORECASE), "compound"),
    (re.compile(r"HTTP 503", re.IGNORECASE), "compound"),
    (re.compile(r"\[TIMEOUT\]", re.IGNORECASE), "timeout"),
    (re.compile(r"timed out.*server did not respond", re.IGNORECASE), "timeout"),
    (re.compile(r"Connection dropped.*server did not respond", re.IGNORECASE), "timeout"),
    (re.compile(r"\[CONTENT FILTERED\]", re.IGNORECASE), "compound"),
    (re.compile(r"content_policy_violation", re.IGNORECASE), "schema"),
    (re.compile(r"This response has been filtered", re.IGNORECASE), "schema"),
    (re.compile(r"<!DOCTYPE html>.*502 Bad Gateway", re.IGNORECASE | re.DOTALL), "compound"),
    (re.compile(r"502 Bad Gateway.*nginx", re.IGNORECASE), "compound"),
    # unicode corruption: 3+ consecutive symbols from Miscellaneous Symbols block
    (re.compile(r"[\u2600-\u26FF]{3,}"), "corrupt"),
]
# mojibake: UTF-8 bytes misread as Latin-1 (e.g., â followed by control chars)
_MOJIBAKE_RE = re.compile(r"â[\x80-\xbf€‚ƒ„…†‡ˆ‰Š‹ŒŽ''" "•–—˜™š›œžŸ]")

# fault types that the detector can output
FAULT_TYPES = ["error", "timeout", "empty", "truncate", "corrupt", "schema", "compound", "unknown"]

# human-readable repair suggestions per fault type
REPAIR_HINTS = {
    "error": "Add retry logic with exponential backoff for HTTP 5xx errors.",
    "timeout": "Set explicit timeouts and implement fallback responses for dropped connections.",
    "empty": "Check for empty/None responses before processing. Add a default fallback.",
    "truncate": "Detect incomplete responses (check finish_reason='length') and request continuation.",
    "corrupt": "Validate response encoding. Add charset checks before parsing LLM output.",
    "schema": "Validate response structure matches expected schema before using content.",
    "compound": "Combine multiple resilience strategies: retry + validate + fallback.",
    "unknown": "Could not determine fault type. Check agent logs for anomalies.",
}


def diagnose(text: str) -> dict:
    """Detect fault type from agent output text.

    Returns: {"fault_type": str, "confidence": str, "hint": str}
    """
    if not text or not text.strip():
        return {"fault_type": "empty", "confidence": "high", "hint": REPAIR_HINTS["empty"]}

    # 1) explicit pattern matching
    for pattern, ftype in RULE_PATTERNS:
        if pattern.search(text):
            return {"fault_type": ftype, "confidence": "high", "hint": REPAIR_HINTS[ftype]}

    # 2) mojibake corruption (2+ hits)
    if len(_MOJIBAKE_RE.findall(text)) >= 2:
        return {"fault_type": "corrupt", "confidence": "high", "hint": REPAIR_HINTS["corrupt"]}

    # 3) truncation: text ends mid-word without punctuation
    t = text.strip()
    if len(t) > 20 and t[-1] not in ".!?`\"')]}>;\n" and t[-1].isalnum():
        last_line = t.split("\n")[-1].strip()
        if len(last_line) > 5 and not last_line.endswith(("TERMINATE", "exitcode")):
            return {"fault_type": "truncate", "confidence": "medium", "hint": REPAIR_HINTS["truncate"]}

    return {"fault_type": "unknown", "confidence": "low", "hint": REPAIR_HINTS["unknown"]}
