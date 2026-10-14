"""Runbook markdown: a small front-matter block and `##` sections.

Front matter is deliberately limited to `key: value` and `key: [a, b]`, so
runbooks never need a full YAML parser.
"""

import re
from dataclasses import dataclass

REQUIRED_SECTIONS = (
    "Scope",
    "Symptoms",
    "Prerequisites",
    "Investigation steps",
    "Safe actions",
    "High-risk actions",
    "Verification",
    "Rollback",
    "Escalation",
)


class RunbookDocumentError(ValueError):
    """The text is not a valid runbook document."""


@dataclass(frozen=True)
class Section:
    heading: str
    body: str


@dataclass(frozen=True)
class RunbookDocument:
    title: str
    services: list[str]
    owner: str | None
    version: int
    sections: list[Section]


def _front_matter(text: str) -> tuple[dict[str, str | list[str]], str]:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise RunbookDocumentError("missing front matter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise RunbookDocumentError("front matter is not closed") from exc
    meta: dict[str, str | list[str]] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise RunbookDocumentError(f"invalid front matter line: {line!r}")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key.strip()] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key.strip()] = value
    return meta, "\n".join(lines[end + 1 :])


def parse(text: str) -> RunbookDocument:
    meta, body = _front_matter(text)
    title = meta.get("title")
    if not isinstance(title, str) or not title:
        raise RunbookDocumentError("front matter needs a title")
    services = meta.get("services", [])
    version = meta.get("version", "1")
    if not isinstance(version, str) or not version.isdigit():
        raise RunbookDocumentError("version must be a positive integer")
    owner = meta.get("owner")

    sections = []
    for match in re.finditer(r"^## +(.+?)\s*$\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL):
        sections.append(Section(match.group(1).strip(), match.group(2).strip()))
    return RunbookDocument(
        title=title,
        services=services if isinstance(services, list) else [services],
        owner=owner if isinstance(owner, str) else None,
        version=int(version),
        sections=sections,
    )
