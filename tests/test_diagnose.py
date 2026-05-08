# tests/test_diagnose.py — Unit tests for fault_diagnose (pure string matching, no network)
from agentchaos.fault_diagnose import FAULT_TYPES, REPAIR_HINTS, diagnose

# ── Empty / None ──────────────────────────────────────────────────


def test_diagnose_empty_string():
    r = diagnose("")
    assert r["fault_type"] == "empty"
    assert r["confidence"] == "high"


def test_diagnose_none_input():
    r = diagnose(None)
    assert r["fault_type"] == "empty"


def test_diagnose_whitespace_only():
    r = diagnose("   \n  ")
    assert r["fault_type"] == "empty"


# ── Error patterns ────────────────────────────────────────────────


def test_diagnose_api_error():
    r = diagnose("[API ERROR] HTTP 500: Internal Server Error.")
    assert r["fault_type"] == "error"


def test_diagnose_http_500():
    r = diagnose("HTTP 500 Internal Server Error occurred")
    assert r["fault_type"] == "error"


# ── Timeout patterns ─────────────────────────────────────────────


def test_diagnose_timeout():
    r = diagnose("[TIMEOUT] The request timed out. The server did not respond within the expected time.")
    assert r["fault_type"] == "timeout"


def test_diagnose_connection_dropped():
    r = diagnose("Connection dropped. The server did not respond.")
    assert r["fault_type"] == "timeout"


# ── Compound patterns ────────────────────────────────────────────


def test_diagnose_service_unavailable():
    r = diagnose("[SERVICE UNAVAILABLE] HTTP 503: The server is temporarily unable to handle the request.")
    assert r["fault_type"] == "compound"


def test_diagnose_content_filtered():
    r = diagnose("[CONTENT FILTERED] This response has been blocked by the content safety filter.")
    assert r["fault_type"] == "compound"


def test_diagnose_502_bad_gateway():
    r = diagnose("<!DOCTYPE html><html><body>502 Bad Gateway nginx/1.24.0</body></html>")
    assert r["fault_type"] == "compound"


# ── Schema patterns ──────────────────────────────────────────────


def test_diagnose_content_policy_violation():
    r = diagnose('{"error": "content_policy_violation", "message": "This response has been filtered."}')
    assert r["fault_type"] == "schema"


# ── Corrupt patterns ─────────────────────────────────────────────


def test_diagnose_unicode_corruption():
    # 4 consecutive symbols from Miscellaneous Symbols block
    r = diagnose("Hello \u2600\u2601\u2602\u2603\u2604 world")
    assert r["fault_type"] == "corrupt"


def test_diagnose_mojibake():
    # simulate UTF-8 bytes misread as Latin-1
    original = "Hello world"
    mojibake = original.encode("utf-8").decode("latin-1")
    # add multiple mojibake patterns
    text = f"{mojibake} â\x80\x99 â\x80\x9c some text"
    r = diagnose(text)
    assert r["fault_type"] == "corrupt"


# ── Truncation detection ─────────────────────────────────────────


def test_diagnose_truncated_text():
    # text ending mid-word without punctuation
    r = diagnose("The answer to the question about prime numbers is that we need to check divisibili")
    assert r["fault_type"] == "truncate"
    assert r["confidence"] == "medium"


def test_diagnose_not_truncated_with_period():
    r = diagnose("The answer is 42.")
    assert r["fault_type"] == "unknown"


def test_diagnose_not_truncated_short():
    r = diagnose("short")
    assert r["fault_type"] == "unknown"


# ── Normal text → unknown ────────────────────────────────────────


def test_diagnose_normal_text():
    r = diagnose("The answer is 42. This is a complete response.")
    assert r["fault_type"] == "unknown"
    assert r["confidence"] == "low"


# ── FAULT_TYPES and REPAIR_HINTS coverage ────────────────────────


def test_all_fault_types_have_hints():
    for ft in FAULT_TYPES:
        assert ft in REPAIR_HINTS


def test_diagnose_returns_hint():
    r = diagnose("[API ERROR] test")
    assert "hint" in r
    assert len(r["hint"]) > 0
