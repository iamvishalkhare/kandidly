"""Console requisition-builder mappings (pure, no IO).

The builder edits screening fields ({type,label,placeholder,required,options})
and rubric criteria ({name,description,weight}); the backend stores them as a
Kandidly JSON-Schema form template (SPEC §8.1) and rubric_criteria rows. Both
directions live here so the round trip is lossless: the original builder type
is stashed in each property's `x-builder-type` (x-* keys are permitted by
validate_template), since `date` and `social` both map onto `short_text`.
"""

from __future__ import annotations

import re

from app.core.errors import AppError

BUILDER_FIELD_TYPES = frozenset(
    {"text", "textarea", "multiple_choice", "multi_select", "range", "date", "file", "social"}
)

_TO_XFIELD = {
    "text": "short_text",
    "textarea": "long_text",
    "multiple_choice": "single_select",
    "multi_select": "multi_select",
    "range": "scale",
    "date": "short_text",
    "file": "file",
    "social": "short_text",
}

_FROM_XFIELD = {
    "short_text": "text",
    "long_text": "textarea",
    "single_select": "multiple_choice",
    "multi_select": "multi_select",
    "scale": "range",
    "number": "text",
    "boolean": "multiple_choice",
    "file": "file",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, fallback: str = "field") -> str:
    slug = _SLUG_RE.sub("_", text.strip().lower()).strip("_")
    return slug[:40] or fallback


def _unique_key(base: str, used: set[str]) -> str:
    key = base
    n = 2
    while key in used:
        key = f"{base}_{n}"
        n += 1
    used.add(key)
    return key


def builder_fields_to_schema(fields: list[dict]) -> dict:
    """Builder screening fields → Kandidly JSON-Schema template.

    Ensures a required `full_name` short_text exists (admin views and the
    display-name hook key off it). The single file field must use the key
    `resume` (validate_template invariant), so the first file field gets it.
    """
    used: set[str] = set()
    properties: dict[str, dict] = {}
    required: list[str] = []
    order: list[str] = []

    has_full_name = any(slugify(f.get("label", "")) == "full_name" for f in fields)
    if not has_full_name:
        properties["full_name"] = {
            "type": "string",
            "title": "Full name",
            "maxLength": 120,
            "x-field": "short_text",
            "x-builder-type": "text",
        }
        required.append("full_name")
        order.append("full_name")
        used.add("full_name")

    for f in fields:
        ftype = f.get("type")
        if ftype not in BUILDER_FIELD_TYPES:
            raise AppError("validation_error", f"unknown screening field type {ftype!r}")
        label = (f.get("label") or "").strip() or "Untitled question"
        key = "resume" if ftype == "file" and "resume" not in used else slugify(label)
        key = _unique_key(key, used)

        prop: dict = {
            "title": label,
            "x-field": _TO_XFIELD[ftype],
            "x-builder-type": ftype,
        }
        placeholder = (f.get("placeholder") or "").strip()
        if placeholder:
            prop["x-placeholder"] = placeholder

        options = [o for o in (f.get("options") or []) if str(o).strip()]
        if ftype == "text" or ftype == "social":
            prop["type"] = "string"
            prop["maxLength"] = 300
        elif ftype == "date":
            prop["type"] = "string"
            prop["maxLength"] = 40
            prop.setdefault("x-placeholder", "YYYY-MM-DD")
        elif ftype == "textarea":
            prop["type"] = "string"
            prop["maxLength"] = 2000
        elif ftype == "multiple_choice":
            prop["type"] = "string"
            prop["enum"] = options or ["Option 1"]
        elif ftype == "multi_select":
            prop["type"] = "array"
            prop["items"] = {"enum": options or ["Option 1"]}
        elif ftype == "range":
            prop["type"] = "integer"
            prop["minimum"] = 1
            prop["maximum"] = 10
        elif ftype == "file":
            prop["type"] = "string"
            prop["x-accept"] = [".pdf", ".docx"]
            prop["x-max-bytes"] = 10485760

        properties[key] = prop
        order.append(key)
        if f.get("required"):
            required.append(key)

    schema: dict = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "x-kandidly": {"profile": "kyi-form/v1", "field_order": order},
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def schema_to_builder_fields(schema: dict) -> list[dict]:
    """Template schema → builder screening fields (inverse of the above)."""
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    order = (schema.get("x-kandidly") or {}).get("field_order") or list(properties)

    fields: list[dict] = []
    for key in order:
        prop = properties.get(key)
        if not isinstance(prop, dict):
            continue
        ftype = prop.get("x-builder-type") or _FROM_XFIELD.get(prop.get("x-field"), "text")
        options = prop.get("enum") or (prop.get("items") or {}).get("enum") or []
        fields.append(
            {
                "id": key,
                "type": ftype,
                "label": prop.get("title") or prop.get("x-label") or key,
                "placeholder": prop.get("x-placeholder") or "",
                "required": key in required,
                "options": list(options),
            }
        )
    return fields


_GENERIC_ANCHORS = [
    {"level": 1, "anchor": "Well below the bar."},
    {"level": 2, "anchor": "Below the bar."},
    {"level": 3, "anchor": "Meets the bar."},
    {"level": 4, "anchor": "Above the bar."},
    {"level": 5, "anchor": "Exceptional."},
]


def builder_rubric_to_criteria(items: list[dict], is_draft: bool = False) -> list[dict]:
    """Builder rubric rows → rubric_criteria dicts (validate_criteria shape).

    The builder collects name/description/weight only; level anchors are
    generic until the builder grows an anchor editor.
    """
    used: set[str] = set()
    criteria: list[dict] = []
    for order, item in enumerate(items, start=1):
        name = (item.get("name") or "").strip()
        if not name:
            if is_draft:
                name = f"Untitled Criterion {order}"
            else:
                raise AppError("validation_error", "rubric criterion name is required")
        criteria.append(
            {
                "key": _unique_key(slugify(name, fallback="criterion"), used),
                "name": name,
                "description": (item.get("description") or "").strip()
                or f"Assessment of {name.lower()}.",
                "weight": float(item.get("weight") or 0),
                "display_order": order,
                "level_anchors": list(_GENERIC_ANCHORS),
            }
        )
    return criteria


def recommendation_for(overall_score: float) -> str:
    """AI decision hint shown on the review page, derived from the 0–100
    overall score (no separate model output exists for this)."""
    if overall_score >= 75.0:
        return "shortlist"
    if overall_score >= 50.0:
        return "hold"
    return "reject"
