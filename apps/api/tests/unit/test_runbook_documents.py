"""Runbook documents: front matter, sections, and the runbooks shipped in docs/."""

from pathlib import Path

import pytest

from opspilot_api.runbooks.document import REQUIRED_SECTIONS, RunbookDocumentError, parse

RUNBOOKS = sorted((Path(__file__).resolve().parents[4] / "docs" / "runbooks").glob("*.md"))
RUNBOOKS = [p for p in RUNBOOKS if p.name != "README.md"]

SAMPLE = """---
title: Checkout high error rate
services: [checkout, storefront]
owner: shop-team
version: 2
---

# Checkout high error rate

## Scope

Checkout fails.

## Symptoms

- errors
"""


def test_parses_front_matter_and_sections() -> None:
    doc = parse(SAMPLE)

    assert (doc.title, doc.services, doc.owner, doc.version) == (
        "Checkout high error rate",
        ["checkout", "storefront"],
        "shop-team",
        2,
    )
    assert [s.heading for s in doc.sections] == ["Scope", "Symptoms"]
    assert doc.sections[1].body == "- errors"


@pytest.mark.parametrize(
    "broken",
    ["# no front matter", "---\ntitle: x\n# never closed", "---\nservices: [a]\n---\n# Untitled"],
)
def test_rejects_documents_without_valid_front_matter(broken: str) -> None:
    with pytest.raises(RunbookDocumentError):
        parse(broken)


def test_environment_defaults_to_all() -> None:
    assert parse(SAMPLE).environment == "all"


def test_environment_comes_from_front_matter() -> None:
    doc = parse(SAMPLE.replace("version: 2\n", "version: 2\nenvironment: production\n"))

    assert doc.environment == "production"


@pytest.mark.parametrize("value", ["[staging, production]", "Production", "prod env", ""])
def test_rejects_an_invalid_environment(value: str) -> None:
    with pytest.raises(RunbookDocumentError, match="environment"):
        parse(SAMPLE.replace("version: 2\n", f"version: 2\nenvironment: {value}\n"))


def test_the_demo_runbooks_exist() -> None:
    assert {p.stem for p in RUNBOOKS} >= {
        "checkout-high-error-rate",
        "payment-timeout",
        "deployment-rollback",
        "pod-crash-loop",
        "database-connection-exhaustion",
        "high-memory-usage",
    }


@pytest.mark.parametrize("path", RUNBOOKS, ids=lambda p: p.stem)
def test_every_runbook_has_the_required_structure(path: Path) -> None:
    doc = parse(path.read_text())

    assert doc.services, "list the services the runbook applies to"
    assert doc.owner
    assert doc.version >= 1
    missing = [s for s in REQUIRED_SECTIONS if s not in {sec.heading for sec in doc.sections}]
    assert not missing, f"missing sections: {missing}"
    assert all(sec.body.strip() for sec in doc.sections), "no empty sections"
