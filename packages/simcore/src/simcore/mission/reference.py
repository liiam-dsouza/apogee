"""The mission config reference page, generated from the Pydantic models.

Every field's description and units already live on the models (and fail the
test suite when missing), so the reference is rendered from the JSON schema
rather than written by hand: it cannot disagree with the API, the UI tooltips
or the validator. ``python -m simcore reference`` prints it; ``make codegen``
writes it to ``docs/reference/mission-config.md`` and CI checks it is current.
"""

import json
from dataclasses import dataclass
from typing import Any

from simcore.mission.models import Mission

HEADER = """# Mission config reference

Every field of a mission file, generated from the models in
`simcore/mission/models.py` by `python -m simcore reference`. Do not edit this
page by hand: change the field's `description` and run `make codegen`.

Units are SI throughout, except angles, which are degrees
([ADR 0001](../adr/0001-angles-in-degrees.md)). Rocket positions are metres
aft of the nose tip ([ADR 0002](../adr/0002-positions-from-nose-tip.md)).
"""


@dataclass
class _Row:
    path: str
    type: str
    units: str
    allowed: str
    default: str
    description: str


class _Renderer:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.defs: dict[str, Any] = schema.get("$defs", {})
        self.variants: list[tuple[str, str, dict[str, Any]]] = []

    def resolve(self, node: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
        """(model name, schema) for a $ref, else (None, node)."""
        ref = node.get("$ref")
        if ref:
            name = ref.rsplit("/", 1)[-1]
            return name, self.defs[name]
        return None, node

    def options(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        """The non-null alternatives of a union (or the node itself)."""
        alts = node.get("anyOf") or node.get("oneOf")
        if not alts:
            return [node]
        # Optional discriminated unions nest: anyOf[oneOf[A, B], null].
        return [o for a in alts if a.get("type") != "null" for o in self.options(a)]

    def type_of(self, node: dict[str, Any]) -> str:
        opts = self.options(node)
        if len(opts) > 1:
            return " or ".join(self.type_of(o) for o in opts)
        node = opts[0]
        name, _ = self.resolve(node)
        if name:
            return name
        if "const" in node:
            return f"`{json.dumps(node['const'])}`"
        if "enum" in node:
            return "one of " + ", ".join(f"`{v}`" for v in node["enum"])
        t = node.get("type")
        if t == "array":
            items = node.get("items", {})
            if "prefixItems" in node:
                inner = ", ".join(self.type_of(i) for i in node["prefixItems"])
                return f"[{inner}]"
            return f"list of {self.type_of(items)}"
        if t == "object":
            extra = node.get("additionalProperties")
            if isinstance(extra, dict) and extra:
                return f"map of string to {self.type_of(extra)}"
            return "mapping"
        if t == "string" and node.get("format") == "date-time":
            return "date-time (UTC)"
        return str(t or "any")

    @staticmethod
    def allowed(node: dict[str, Any]) -> str:
        parts = []
        for key, symbol in (
            ("exclusiveMinimum", ">"),
            ("minimum", "≥"),
            ("exclusiveMaximum", "<"),
            ("maximum", "≤"),
        ):
            if key in node:
                parts.append(f"{symbol} {node[key]:g}")
        if node.get("minLength") == 1:
            parts.append("not empty")
        if "minItems" in node and node.get("maxItems") != node["minItems"]:
            parts.append("not empty" if node["minItems"] == 1 else f"at least {node['minItems']}")
        return ", ".join(parts)

    def rows(self, node: dict[str, Any], prefix: str, seen: tuple[str, ...]) -> list[_Row]:
        out: list[_Row] = []
        required = set(node.get("required", []))
        for name, prop in node.get("properties", {}).items():
            path = f"{prefix}.{name}" if prefix else name
            opts = self.options(prop)
            single = opts[0] if len(opts) == 1 else None
            target = single
            child = path
            if single and single.get("type") == "array":
                target = single.get("items", {})
                child = f"{path}[]"
            elif single and isinstance(single.get("additionalProperties"), dict):
                target = single["additionalProperties"]
                child = f"{path}.<key>"
            ref_name, resolved = self.resolve(target) if target else (None, {})
            constraints = {**(single or {}), **prop}
            if "default" in prop:
                default = f"`{json.dumps(prop['default'])}`"
            elif name in required:
                default = "required"
            elif name in ("id", "created_utc"):
                default = "generated"
            else:
                default = ""
            out.append(
                _Row(
                    path=path,
                    type=self.type_of(prop),
                    units=prop.get("units") or (single or {}).get("units", ""),
                    allowed=self.allowed(constraints),
                    default=default,
                    description=prop.get("description", ""),
                )
            )
            if ref_name and ref_name not in seen and resolved.get("properties"):
                out.extend(self.rows(resolved, child, (*seen, ref_name)))
            elif len(opts) > 1:
                for opt in opts:
                    opt_name, opt_schema = self.resolve(opt)
                    if opt_name and opt_name not in seen and opt_schema.get("properties"):
                        self.variants.append((path, opt_name, opt_schema))
        return out

    @staticmethod
    def table(rows: list[_Row]) -> str:
        def cell(text: str) -> str:
            return text.replace("|", "\\|").replace("\n", " ")

        lines = [
            "| Field | Type | Units | Allowed | Default | Description |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| `{r.path}` | {cell(r.type)} | {r.units} | {r.allowed} | {r.default} "
            f"| {cell(r.description)} |"
            for r in rows
        ]
        return "\n".join(lines)


def render_reference() -> str:
    """The reference page as Markdown."""
    schema = Mission.model_json_schema()
    r = _Renderer(schema)
    out = [HEADER]
    for name, prop in schema["properties"].items():
        r.variants.clear()
        section_rows = r.rows(
            {"properties": {name: prop}, "required": schema.get("required", [])}, "", ("Mission",)
        )
        out.append(f"## `{name}`\n")
        out.append(prop.get("description", "") + "\n")
        out.append(r.table(section_rows) + "\n")
        done: set[tuple[str, str]] = set()
        while r.variants:
            path, model, variant = r.variants.pop(0)
            if (path, model) in done:
                continue
            done.add((path, model))
            out.append(f"### `{path}` as {model}\n")
            if variant.get("description"):
                out.append(variant["description"].strip() + "\n")
            out.append(r.table(r.rows(variant, path, ("Mission", model))) + "\n")
    return "\n".join(out).rstrip() + "\n"
