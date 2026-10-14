import pytest

from opspilot_api.rate_limit import Policy, classify


@pytest.mark.parametrize(
    ("method", "route", "policy"),
    [
        ("GET", "/api/v1/incidents", Policy.READ),
        ("HEAD", "/api/v1/incidents/{incident_id}", Policy.READ),
        ("POST", "/api/v1/incidents", Policy.WRITE),
        ("PATCH", "/api/v1/incidents/{incident_id}", Policy.WRITE),
        ("PUT", "/api/v1/runbooks/{runbook_id}", Policy.WRITE),
        ("POST", "/api/v1/proposals/{proposal_id}/approve", Policy.SENSITIVE),
        ("POST", "/api/v1/proposals/{proposal_id}/reject", Policy.SENSITIVE),
        ("POST", "/api/v1/models/{model_id}/promote", Policy.SENSITIVE),
        ("POST", "/api/v1/incidents/{incident_id}/investigation", Policy.SENSITIVE),
        ("POST", "/api/v1/incidents/{incident_id}/postmortem", Policy.SENSITIVE),
        ("POST", "/api/v1/runbooks/reindex", Policy.SENSITIVE),
        ("GET", "/api/v1/incidents/{incident_id}/investigation", Policy.READ),
    ],
)
def test_routes_are_classified_by_method_and_template(
    method: str, route: str, policy: Policy
) -> None:
    assert classify(method, route) is policy
