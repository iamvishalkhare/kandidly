"""Form template engine (SPEC §8.1). validate_template + validate_field_hints run
on create AND publish; validate_submission checks candidate answers on submit.

Pure functions raising AppError(code='validation_error') with a field detail so
the builder UI can surface errors inline (SPEC §13.3)."""

from __future__ import annotations

from typing import Any

import jsonschema

from app.core.errors import AppError

# §8.1.1 — the only supported field types.
FIELD_TYPES: frozenset[str] = frozenset(
    {
        "short_text",
        "long_text",
        "single_select",
        "multi_select",
        "scale",
        "number",
        "boolean",
        "file",
    }
)

# §8.1.2 — whitelist of JSON-Schema keywords (plus any x-* extension).
ALLOWED_KEYWORDS: frozenset[str] = frozenset(
    {
        "type",
        "title",
        "description",
        "maxLength",
        "minLength",
        "minimum",
        "maximum",
        "items",
        "enum",
        "required",
        "properties",
        "$schema",
    }
)

MAX_FIELDS = 40
HINT_ROLES: frozenset[str] = frozenset({"difficulty_signal", "seed_topic", "context"})


def _fail(message: str, **detail: Any) -> AppError:
    return AppError("validation_error", message, detail=detail)


def _check_keywords(obj: dict, where: str) -> None:
    for key in obj:
        if key.startswith("x-"):
            continue
        if key not in ALLOWED_KEYWORDS:
            raise _fail(f"Unknown JSON-Schema keyword {key!r} in {where}", keyword=key, where=where)


def validate_template(schema: dict) -> None:
    """Validate a Kandidly JSON-Schema profile (SPEC §8.1.2)."""
    if not isinstance(schema, dict):
        raise _fail("schema must be an object")
    if schema.get("type") != "object":
        raise _fail("top-level type must be 'object'")

    x_kandidly = schema.get("x-kandidly")
    if not isinstance(x_kandidly, dict) or "field_order" not in x_kandidly:
        raise _fail("x-kandidly.field_order is required")

    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise _fail("properties is required and non-empty")

    if len(properties) > MAX_FIELDS:
        raise _fail(f"too many fields ({len(properties)} > {MAX_FIELDS})")

    _check_keywords(schema, "root")

    file_fields: list[str] = []
    for key, prop in properties.items():
        if not isinstance(prop, dict):
            raise _fail(f"property {key!r} must be an object", field=key)
        _check_keywords(prop, key)

        x_field = prop.get("x-field")
        if x_field not in FIELD_TYPES:
            raise _fail(f"property {key!r} has invalid or missing x-field", field=key)
        title = prop.get("title")
        if not isinstance(title, str) or not title.strip():
            raise _fail(f"property {key!r} needs a non-empty title", field=key)
        if x_field == "file":
            file_fields.append(key)
        if x_field == "scale":
            mx = prop.get("maximum")
            if not isinstance(mx, int) or not (1 <= mx <= 10):
                raise _fail(f"scale field {key!r} needs integer maximum in 1..10", field=key)

    # At most one file field; if present its key MUST be 'resume'.
    if len(file_fields) > 1:
        raise _fail("at most one file field is allowed", fields=file_fields)
    if file_fields and file_fields[0] != "resume":
        raise _fail("the file field's key MUST be 'resume'", field=file_fields[0])

    # field_order lists every property key exactly once.
    field_order = x_kandidly["field_order"]
    if not isinstance(field_order, list) or sorted(field_order) != sorted(properties):
        raise _fail(
            "x-kandidly.field_order must list every property key exactly once",
            field_order=field_order,
            properties=list(properties),
        )
    if len(set(field_order)) != len(field_order):
        raise _fail("x-kandidly.field_order contains duplicates")


def validate_field_hints(schema: dict, field_hints: dict) -> None:
    """SPEC §8.1.3 — hint keys must be a subset of schema properties; roles valid."""
    properties = set(schema.get("properties", {}))
    for key, hint in (field_hints or {}).items():
        if key not in properties:
            raise _fail(f"field_hints references unknown field {key!r}", field=key)
        if not isinstance(hint, dict):
            raise _fail(f"field_hints[{key!r}] must be an object", field=key)
        if hint.get("use_in_plan"):
            role = hint.get("role")
            if role is not None and role not in HINT_ROLES:
                raise _fail(f"field_hints[{key!r}].role invalid: {role!r}", field=key)


def _jsonschema_view(schema: dict) -> dict:
    """Strip x-* extension keywords so the stock validator accepts the schema.
    File fields are stored as the stored_files.id (uuid string) — typed as string."""

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if not k.startswith("x-")}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(schema)


def validate_submission(schema: dict, answers: dict) -> None:
    """Validate final answers against the template schema (SPEC §8.1.2)."""
    view = _jsonschema_view(schema)
    try:
        jsonschema.validate(instance=answers, schema=view)
    except jsonschema.ValidationError as exc:
        raise _fail(
            "form answers failed validation",
            error=exc.message,
            path=list(exc.absolute_path),
        ) from exc
