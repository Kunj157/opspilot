#!/usr/bin/env python3
"""Render docs/api/reference.md from the committed OpenAPI schema.

The schema (packages/api-client/openapi.json) is exported from the FastAPI app
by `make api-client`, so this needs only the standard library: no running
services and no API dependencies. Run it through `make api-docs`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "packages" / "api-client" / "openapi.json"
OUT = ROOT / "docs" / "api" / "reference.md"
METHODS = ("get", "post", "put", "patch", "delete")


def type_of(schema: dict) -> str:
    if "$ref" in schema:
        return f"[{schema['$ref'].rsplit('/', 1)[-1]}](#{schema['$ref'].rsplit('/', 1)[-1].lower()})"
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return " or ".join(type_of(s) for s in schema[key])
    if "enum" in schema:
        return " / ".join(f"`{v}`" for v in schema["enum"])
    kind = schema.get("type", "object")
    if kind == "array":
        return f"array of {type_of(schema.get('items', {}))}"
    fmt = schema.get("format")
    return f"{kind} ({fmt})" if fmt else kind


def cell(text: object) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def render(spec: dict) -> str:
    info = spec["info"]
    out = [
        f"# {info['title']} reference",
        "",
        "Generated from the OpenAPI schema by "
        "`make api-docs`; do not edit by hand. The machine-readable schema is "
        "[`packages/api-client/openapi.json`](../../packages/api-client/openapi.json), "
        "and a running API serves it at `/openapi.json` with interactive docs at `/docs`.",
        "",
        "## Conventions",
        "",
        "- Every route lives under `/api/v1`. Send `Authorization: Bearer <access token>` "
        "on everything except the health checks. `scripts/dev-token.sh` prints a token "
        "for the local Keycloak realm.",
        "- Roles are enforced per route by a permission dependency; a missing token is "
        "401 and an insufficient role is 403. Resources of another organization return 404.",
        "- Every mutation accepts an `Idempotency-Key` header; a replay returns the "
        "stored response.",
        "- Rate limits return 429 with `Retry-After`. Validation errors return 422.",
        "",
    ]
    by_tag: dict[str, list[tuple[str, str, dict]]] = {}
    for path, item in spec["paths"].items():
        for method in METHODS:
            op = item.get(method)
            if op:
                by_tag.setdefault((op.get("tags") or ["other"])[0], []).append((method, path, op))

    out += ["## Endpoints", "", "| Tag | Operations |", "|---|---|"]
    out += [f"| [{t}](#{t}) | {len(ops)} |" for t, ops in sorted(by_tag.items())]
    out.append("")
    for tag, ops in sorted(by_tag.items()):
        out += [f"### {tag}", ""]
        for method, path, op in ops:
            out += [f"#### `{method.upper()} {path}`", ""]
            out.append(f"{op.get('summary', '')}.")
            if op.get("description"):
                out += ["", op["description"].strip()]
            out.append("")
            out.append("Auth: " + ("bearer token" if op.get("security") else "none"))
            params = op.get("parameters", [])
            if params:
                out += ["", "| Parameter | In | Type | Required | Description |", "|---|---|---|---|---|"]
                for p in params:
                    out.append(
                        f"| `{p['name']}` | {p['in']} | {cell(type_of(p.get('schema', {})))} "
                        f"| {'yes' if p.get('required') else 'no'} | {cell(p.get('description'))} |"
                    )
            body = op.get("requestBody", {}).get("content", {}).get("application/json")
            if body:
                out += ["", f"Request body: {type_of(body.get('schema', {}))}"]
            out += ["", "| Status | Description | Body |", "|---|---|---|"]
            for status, resp in op.get("responses", {}).items():
                content = resp.get("content", {}).get("application/json", {})
                out.append(
                    f"| {status} | {cell(resp.get('description'))} "
                    f"| {cell(type_of(content['schema'])) if content.get('schema') else ''} |"
                )
            out.append("")
    out += ["## Schemas", ""]
    for name, schema in sorted(spec.get("components", {}).get("schemas", {}).items()):
        out += [f"### {name}", ""]
        if schema.get("description"):
            out += [schema["description"].strip(), ""]
        props = schema.get("properties")
        if props:
            required = set(schema.get("required", []))
            out += ["| Field | Type | Required | Description |", "|---|---|---|---|"]
            for field, fs in props.items():
                out.append(
                    f"| `{field}` | {cell(type_of(fs))} | {'yes' if field in required else 'no'} "
                    f"| {cell(fs.get('description'))} |"
                )
        elif "enum" in schema:
            out.append("One of: " + ", ".join(f"`{v}`" for v in schema["enum"]))
        else:
            out.append(f"Type: {type_of(schema)}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(json.loads(SCHEMA.read_text())))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
