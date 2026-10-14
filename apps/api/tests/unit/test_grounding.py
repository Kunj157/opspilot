"""Summary grounding: every claim cites collected evidence, or is marked unverified."""

from opspilot_api.agents.grounding import ground_summary

KNOWN = {"E1", "E2", "E3"}


def test_cited_claims_are_kept_as_they_are() -> None:
    result = ground_summary("Checkout 1.4.2 fails (E1, E3). Errors began at 10:02 [E2].", KNOWN)

    assert result.summary == "Checkout 1.4.2 fails (E1, E3). Errors began at 10:02 [E2]."
    assert (result.dropped, result.unverified) == (0, 0)


def test_claims_citing_unknown_evidence_are_dropped() -> None:
    result = ground_summary("Checkout fails (E1). The database is down (E2, E9).", KNOWN)

    assert result.summary == "Checkout fails (E1)."
    assert result.dropped == 1


def test_uncited_claims_are_marked_and_unknowns_left_alone() -> None:
    result = ground_summary(
        "Traffic doubled! Unknown: the trigger. Unverified: maybe DNS? Version 1.4.2 is new (E1).",
        KNOWN,
    )

    assert result.summary == (
        "Unverified: Traffic doubled! Unknown: the trigger. Unverified: maybe DNS? "
        "Version 1.4.2 is new (E1)."
    )
    assert result.unverified == 1


def test_an_empty_summary_stays_empty() -> None:
    assert ground_summary("  ", KNOWN).summary == ""
