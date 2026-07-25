"""
Natural-Language Route Parser

Turns a free-text request like:
    "fastest way to Whitefield from Koramangala avoiding tolls and Outer Ring Road"
into structured fields:
    { "origin": "Koramangala", "destination": "Whitefield", "avoid": ["tolls", "Outer Ring Road"] }

Follows the same resilience pattern already used for TomTom/geocoding
elsewhere in this backend: try the real thing first (here, an LLM call to
Claude), fall back to something deterministic and dependency-free if it's
unavailable, so the feature never hard-fails just because a key isn't set.

Set ANTHROPIC_API_KEY in .env to enable real LLM parsing (handles much
messier phrasing — typos, implied destinations, multiple constraints).
Without a key, a regex-based parser handles the common patterns
("X to Y", "from X to Y", "avoid(ing) <thing>") — no external dependency,
which is also what runs in this environment's tests below.
"""

import os
import re
import json
from typing import Optional

try:
    import httpx
except ImportError:  # httpx is already a project dependency, this is just defensive
    httpx = None

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-6"  # cheap + fast is plenty for a small extraction task

SYSTEM_PROMPT = """You extract structured route info from a driver's natural-language request.
Return ONLY a JSON object, no other text, in exactly this shape:
{"origin": "<string or null>", "destination": "<string or null>", "avoid": ["<string>", ...]}

- origin/destination should be place names as written (don't invent ones not implied by the text).
- avoid should list any roads, route types (e.g. "tolls", "highways"), or areas the driver wants to avoid. Empty list if none mentioned.
- If origin isn't mentioned at all, set it to null (the caller will fall back to current location).
"""


def _rule_based_parse(text: str) -> dict:
    """Deterministic fallback: handles common phrasings without any LLM call."""
    original = text.strip()
    lower = original.lower()

    avoid = []
    avoid_match = re.search(r"avoid(?:ing)?\s+(.+?)(?:\.|$)", lower)
    if avoid_match:
        # Split on "and"/commas to catch multiple avoided things
        pieces = re.split(r",|\band\b", avoid_match.group(1))
        avoid = [p.strip() for p in pieces if p.strip()]
        # Strip the avoid clause out before looking for origin/destination
        lower = lower[:avoid_match.start()].strip()

    origin, destination = None, None

    # Precedence: patterns that unambiguously specify BOTH origin and
    # destination win over filler-phrase (destination-only) handling —
    # e.g. "fastest way to Whitefield from Koramangala" has a filler prefix
    # AND an explicit origin, so it must not be treated as destination-only.
    m = re.search(r"\bto\s+(.+?)\s+from\s+(.+)", lower)
    if m:
        destination, origin = m.group(1).strip(), m.group(2).strip()
    else:
        m = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+)", lower)
        if m:
            origin, destination = m.group(1).strip(), m.group(2).strip()
        else:
            # No explicit "from" anywhere — check destination-only filler phrases
            # ("take me to X", "navigate to X", "fastest way to X") before falling
            # back to a generic "X to Y" split.
            filler_m = re.match(
                r"^(?:take me|navigate|go|drive|get)\s+to\s+(.+)|"
                r"^(?:fastest|quickest|best|shortest)\s+(?:way|route)\s+to\s+(.+)",
                lower,
            )
            if filler_m:
                destination = (filler_m.group(1) or filler_m.group(2)).strip()
            else:
                m = re.search(r"(.+?)\s+to\s+(.+)", lower)
                if m:
                    origin, destination = m.group(1).strip(), m.group(2).strip()
                else:
                    destination = lower.strip() or None

    # Clean up filler words/prefixes that can survive at the edges
    def clean(s):
        if not s:
            return s
        s = re.sub(r"^(the|way|route|to|fastest|quickest|best)\s+", "", s).strip()
        return s.title() if s else s

    return {
        "origin": clean(origin),
        "destination": clean(destination),
        "avoid": avoid,
        "source": "rule_based",
    }


def _llm_parse(text: str) -> Optional[dict]:
    """Real LLM parse via Claude. Returns None on any failure so the caller
    falls back to the rule-based parser instead of raising."""
    if not ANTHROPIC_API_KEY or httpx is None:
        return None
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 200,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": text}],
            },
            timeout=8.0,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()
        # Defensive: strip markdown fences if the model adds them despite instructions
        raw_text = re.sub(r"^```(?:json)?|```$", "", raw_text.strip()).strip()
        parsed = json.loads(raw_text)
        parsed["source"] = "llm"
        return parsed
    except Exception as e:
        print(f"[NLU] LLM parse failed, falling back to rule-based: {e}")
        return None


def parse_request(text: str) -> dict:
    """Public entry point. Always returns a dict with origin/destination/avoid/source."""
    result = _llm_parse(text)
    if result is None:
        result = _rule_based_parse(text)
    result.setdefault("avoid", [])
    return result
