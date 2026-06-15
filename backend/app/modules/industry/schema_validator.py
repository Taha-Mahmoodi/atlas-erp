"""A compact, dependency-free JSON-Schema validator (PLAN 14.1 / D-060).

The industry loader validates every template against ``industry-templates/_schema.yaml`` — the
declarative single source of truth — BEFORE parsing it into the Pydantic models. To avoid pulling
in the ``jsonschema`` package for the small Draft-2020-12 subset the schema uses, this module
implements exactly that subset:

    type (incl. union [..]), enum, const-via-enum, required, properties, additionalProperties
    (bool OR a sub-schema for the numbering_formats map), items, minItems, minProperties,
    minLength, maxLength, pattern, minimum, maximum.

It raises ``IndustrySchemaError`` (an AtlasError -> 422) with a JSON-pointer-style ``path`` so a
malformed template names the exact offending field. Anything outside the supported subset in the
schema would raise ``UnsupportedSchemaError`` rather than silently passing — so the validator can
never give a false PASS on a keyword it does not understand.
"""

import re
from typing import Any

from app.core.exceptions import AtlasError

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}

# Schema keywords this validator understands. Anything else in the schema is a build error
# (UnsupportedSchemaError) — never a silent pass.
_SUPPORTED_KEYWORDS = frozenset(
    {
        "type", "enum", "required", "properties", "additionalProperties", "items", "minItems",
        "minProperties", "minLength", "maxLength", "pattern", "minimum", "maximum",
        # Documentation-only keywords ignored during validation:
        "$schema", "$id", "title", "description",
    }
)


class IndustrySchemaError(AtlasError):
    """A template failed JSON-Schema validation against _schema.yaml (D-060). Surfaced as 422
    ``industry.schema_invalid`` with the offending JSON path so the author sees exactly where."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(
            code="industry.schema_invalid",
            message=f"{path or '<root>'}: {message}",
            status_code=422,
            details={"path": path, "reason": message},
        )


class UnsupportedSchemaError(AtlasError):
    """The schema used a keyword this minimal validator does not implement — a developer error in
    _schema.yaml, not a template error. Surfaced as 500 so it is caught in CI, never shipped."""

    def __init__(self, keyword: str) -> None:
        super().__init__(
            code="industry.schema_unsupported_keyword",
            message=f"_schema.yaml uses unsupported JSON-Schema keyword {keyword!r}",
            status_code=500,
        )


def _join(path: str, key: Any) -> str:
    return f"{path}/{key}" if path else f"/{key}"


def _check_type(value: Any, type_spec: Any, path: str) -> None:
    allowed = type_spec if isinstance(type_spec, list) else [type_spec]
    for name in allowed:
        check = _TYPE_CHECKS.get(name)
        if check is None:
            raise UnsupportedSchemaError(f"type:{name}")
        if check(value):
            return
    raise IndustrySchemaError(path, f"expected type {type_spec}, got {type(value).__name__}")


def _validate(value: Any, schema: dict[str, Any], path: str) -> None:
    unsupported = set(schema) - _SUPPORTED_KEYWORDS
    if unsupported:
        raise UnsupportedSchemaError(sorted(unsupported)[0])

    if "type" in schema:
        _check_type(value, schema["type"], path)
    if "enum" in schema and value not in schema["enum"]:
        raise IndustrySchemaError(path, f"{value!r} is not one of {schema['enum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise IndustrySchemaError(path, f"shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise IndustrySchemaError(path, f"longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise IndustrySchemaError(path, f"does not match pattern {schema['pattern']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise IndustrySchemaError(path, f"less than minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise IndustrySchemaError(path, f"greater than maximum {schema['maximum']}")

    if isinstance(value, dict):
        _validate_object(value, schema, path)
    if isinstance(value, list):
        _validate_array(value, schema, path)


def _validate_object(value: dict[str, Any], schema: dict[str, Any], path: str) -> None:
    for required_key in schema.get("required", ()):
        if required_key not in value:
            raise IndustrySchemaError(path, f"missing required property {required_key!r}")
    if "minProperties" in schema and len(value) < schema["minProperties"]:
        raise IndustrySchemaError(path, f"fewer than minProperties {schema['minProperties']}")
    properties = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)
    for key, item in value.items():
        if key in properties:
            _validate(item, properties[key], _join(path, key))
        elif additional is False:
            raise IndustrySchemaError(_join(path, key), "additional property is not allowed")
        elif isinstance(additional, dict):
            # The numbering_formats map: every extra key's VALUE follows the additional sub-schema.
            _validate(item, additional, _join(path, key))


def _validate_array(value: list[Any], schema: dict[str, Any], path: str) -> None:
    if "minItems" in schema and len(value) < schema["minItems"]:
        raise IndustrySchemaError(path, f"fewer than minItems {schema['minItems']}")
    item_schema = schema.get("items")
    if item_schema is not None:
        for index, item in enumerate(value):
            _validate(item, item_schema, _join(path, index))


def validate_against_schema(document: Any, schema: dict[str, Any]) -> None:
    """Validate ``document`` against the JSON-Schema ``schema`` (the parsed _schema.yaml).

    Raises ``IndustrySchemaError`` (422) on the first violation with its JSON path, or
    ``UnsupportedSchemaError`` (500) if the schema uses a keyword this validator does not implement
    (a build error caught in CI)."""
    _validate(document, schema, "")
