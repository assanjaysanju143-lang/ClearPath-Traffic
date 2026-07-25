"""
Tests for services/nlu.py's rule-based fallback parser (the path that runs
without ANTHROPIC_API_KEY set — no network calls, so safe to run in CI).
"""

from services.nlu import parse_request


def test_from_x_to_y():
    r = parse_request("from Indiranagar to Electronic City")
    assert r["origin"] == "Indiranagar"
    assert r["destination"] == "Electronic City"
    assert r["avoid"] == []
    assert r["source"] == "rule_based"


def test_generic_x_to_y():
    r = parse_request("MG Road to Marathahalli")
    assert r["origin"] == "Mg Road"
    assert r["destination"] == "Marathahalli"


def test_destination_first_then_origin_with_from():
    """Regression test: 'fastest way to X from Y' has 'to' before 'from',
    which is the reverse of the usual 'from Y to X' ordering — this
    previously mis-parsed as taking the filler words as the origin."""
    r = parse_request("fastest way to Whitefield from Koramangala")
    assert r["origin"] == "Koramangala"
    assert r["destination"] == "Whitefield"


def test_filler_phrase_take_me_to_is_destination_only():
    """Regression test: 'take me to X' previously parsed 'take me' as a
    (nonsensical) origin instead of recognizing it as a destination-only
    filler phrase."""
    r = parse_request("take me to Whitefield")
    assert r["origin"] is None
    assert r["destination"] == "Whitefield"


def test_filler_phrase_navigate_to():
    r = parse_request("navigate to Jayanagar")
    assert r["origin"] is None
    assert r["destination"] == "Jayanagar"


def test_filler_phrase_quickest_route_to():
    r = parse_request("quickest route to BTM Layout")
    assert r["origin"] is None
    assert r["destination"] == "Btm Layout"


def test_avoid_single_term():
    r = parse_request("Koramangala to HSR Layout avoiding Sarjapur Road")
    assert r["avoid"] == ["sarjapur road"]
    assert r["origin"] == "Koramangala"
    assert r["destination"] == "Hsr Layout"


def test_avoid_multiple_terms_joined_by_and():
    r = parse_request("fastest way to Whitefield from Koramangala avoiding tolls and Outer Ring Road")
    assert "tolls" in r["avoid"]
    assert "outer ring road" in r["avoid"]
    assert r["origin"] == "Koramangala"
    assert r["destination"] == "Whitefield"


def test_no_to_keyword_falls_back_to_destination_only():
    r = parse_request("Whitefield")
    assert r["destination"] == "Whitefield"


def test_source_is_always_present():
    r = parse_request("anything at all")
    assert r["source"] == "rule_based"
    assert "avoid" in r
