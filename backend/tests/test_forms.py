"""Form template validation (SPEC §8.1.2, §18.1). Each rule has a failing
fixture."""

from __future__ import annotations

import copy

import pytest

from app.core.errors import AppError
from app.domain.forms import validate_field_hints, validate_submission, validate_template

VALID = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "x-kandidly": {"profile": "kyi-form/v1", "field_order": ["full_name", "resume"]},
    "required": ["full_name", "resume"],
    "properties": {
        "full_name": {
            "type": "string",
            "title": "Full name",
            "maxLength": 120,
            "x-field": "short_text",
        },
        "resume": {
            "type": "string",
            "title": "Upload your resume",
            "x-field": "file",
            "x-accept": [".pdf"],
            "x-max-bytes": 10485760,
        },
    },
}


def test_valid_template_passes():
    validate_template(copy.deepcopy(VALID))


def test_missing_x_field_rejected():
    bad = copy.deepcopy(VALID)
    del bad["properties"]["full_name"]["x-field"]
    with pytest.raises(AppError):
        validate_template(bad)


def test_empty_title_rejected():
    bad = copy.deepcopy(VALID)
    bad["properties"]["full_name"]["title"] = "  "
    with pytest.raises(AppError):
        validate_template(bad)


def test_field_order_must_match_properties():
    bad = copy.deepcopy(VALID)
    bad["x-kandidly"]["field_order"] = ["full_name"]  # missing resume
    with pytest.raises(AppError):
        validate_template(bad)


def test_file_field_must_be_named_resume():
    bad = copy.deepcopy(VALID)
    bad["properties"]["cv"] = bad["properties"].pop("resume")
    bad["x-kandidly"]["field_order"] = ["full_name", "cv"]
    with pytest.raises(AppError):
        validate_template(bad)


def test_two_file_fields_rejected():
    bad = copy.deepcopy(VALID)
    bad["properties"]["resume2"] = {"type": "string", "title": "Second", "x-field": "file"}
    bad["x-kandidly"]["field_order"] = ["full_name", "resume", "resume2"]
    with pytest.raises(AppError):
        validate_template(bad)


def test_unknown_keyword_rejected():
    bad = copy.deepcopy(VALID)
    bad["properties"]["full_name"]["pattern"] = ".*"  # not whitelisted, not x-*
    with pytest.raises(AppError):
        validate_template(bad)


def test_scale_bounds_enforced():
    bad = copy.deepcopy(VALID)
    bad["properties"]["rating"] = {
        "type": "integer",
        "title": "R",
        "x-field": "scale",
        "minimum": 1,
        "maximum": 20,
    }
    bad["x-kandidly"]["field_order"] = ["full_name", "rating", "resume"]
    with pytest.raises(AppError):
        validate_template(bad)


def test_field_hints_unknown_field_rejected():
    with pytest.raises(AppError):
        validate_field_hints(VALID, {"nonexistent": {"use_in_plan": True}})


def test_field_hints_bad_role_rejected():
    with pytest.raises(AppError):
        validate_field_hints(VALID, {"full_name": {"use_in_plan": True, "role": "bogus"}})


def test_submission_validation():
    validate_submission(VALID, {"full_name": "Ada", "resume": "some-uuid"})
    with pytest.raises(AppError):
        validate_submission(VALID, {"resume": "x"})  # missing required full_name
