"""Give an incident a pending rollback proposal, as the remediation agent would.

    uv run --directory apps/api python ../../tests/e2e/fixtures/seed_proposal.py <incident id>

Browser tests use it because proposals only come from agents, and the e2e
stack runs no worker or model. Needs DATABASE_URL.
"""

import json
import os
import sys

import psycopg


def main(incident_id: str) -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        conn.execute(
            "update incidents set status = 'AWAITING_APPROVAL', version = version + 1 "
            "where id = %s",
            (incident_id,),
        )
        conn.execute(
            """
            insert into remediation_proposals
                (organization_id, incident_id, action_type, description, parameters,
                 risk_level, verification_plan, expires_at)
            select organization_id, id, 'ROLLBACK_DEPLOYMENT',
                   'Errors began with release 1.4.2', %s, 'medium', %s,
                   now() + interval '30 minutes'
            from incidents where id = %s
            """,
            (
                json.dumps(
                    {
                        "namespace": "demo",
                        "deployment": "checkout",
                        "to_revision": 6,
                        "from_version": "1.4.2",
                        "to_version": "1.0.0",
                    }
                ),
                json.dumps({"window_minutes": 3, "max_error_rate": 0.02}),
                incident_id,
            ),
        )


if __name__ == "__main__":
    main(sys.argv[1])
