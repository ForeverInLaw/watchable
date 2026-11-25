"""The protocol contract: every example in protocol/examples passes its schema.

An example is named `<schema>[.<variant>].json` and checked against
`protocol/schema/<schema>.schema.json`. Schemas reference each other by file name.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

PROTOCOL = Path(__file__).resolve().parents[2] / "protocol"
SCHEMAS = sorted((PROTOCOL / "schema").glob("*.schema.json"))
EXAMPLES = sorted((PROTOCOL / "examples").glob("*.json"))


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


REGISTRY: Registry[Any] = Registry().with_resources(
    (path.name, Resource.from_contents(load(path))) for path in SCHEMAS
)


def validator(schema_file: str) -> Draft202012Validator:
    """Validator for a schema in protocol/schema, with format checks on."""
    return Draft202012Validator(
        {"$ref": schema_file},
        registry=REGISTRY,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def schema_file_of(example: Path) -> str:
    return f"{example.name.split('.')[0]}.schema.json"


def test_every_schema_has_an_example() -> None:
    covered = {schema_file_of(example) for example in EXAMPLES}

    assert SCHEMAS
    assert {path.name for path in SCHEMAS} <= covered


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda path: path.name)
def test_schema_is_valid_json_schema(schema: Path) -> None:
    Draft202012Validator.check_schema(load(schema))


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda path: path.name)
def test_example_passes_its_schema(example: Path) -> None:
    validator(schema_file_of(example)).validate(load(example))


COMPANION_SCHEMA = "notification-event.schema.json"
WATCH_SCHEMA = "notification-event-watch.schema.json"
COMPANION_EVENT: dict[str, Any] = load(PROTOCOL / "examples" / "notification-event.json")
WATCH_EVENT: dict[str, Any] = load(
    PROTOCOL / "examples" / "notification-event-watch.truncated.json"
)


def without(event: dict[str, Any], key: str) -> dict[str, Any]:
    return {name: value for name, value in event.items() if name != key}


@pytest.mark.parametrize(
    ("schema_file", "event", "keyword"),
    [
        (COMPANION_SCHEMA, COMPANION_EVENT | {"posted_at": "2026-11-24T15:00:00+03:00"}, "pattern"),
        (COMPANION_SCHEMA, COMPANION_EVENT | {"event_id": "018f"}, "format"),
        (COMPANION_SCHEMA, without(COMPANION_EVENT, "notification_key"), "required"),
        (COMPANION_SCHEMA, COMPANION_EVENT | {"body_truncated": False}, "unevaluatedProperties"),
        (WATCH_SCHEMA, WATCH_EVENT | {"body": "a" * 3001}, "maxLength"),
        (WATCH_SCHEMA, WATCH_EVENT | {"body": "Привет"}, "minLength"),
        (WATCH_SCHEMA, WATCH_EVENT | {"body": None}, "type"),
        (WATCH_SCHEMA, without(WATCH_EVENT, "body_truncated"), "required"),
        (WATCH_SCHEMA, WATCH_EVENT | {"body_full": "a" * 3001}, "unevaluatedProperties"),
    ],
    ids=[
        "companion: posted_at not in UTC",
        "companion: event_id not a UUID",
        "companion: no notification_key",
        "companion: unknown field",
        "watch: body over 3000",
        "watch: truncated body under 3000",
        "watch: truncated null body",
        "watch: no body_truncated",
        "watch: unknown field",
    ],
)
def test_schema_rejects(schema_file: str, event: dict[str, Any], keyword: str) -> None:
    errors = validator(schema_file).iter_errors(event)

    assert keyword in {error.validator for error in errors}


def test_companion_event_carries_the_full_body() -> None:
    validator(COMPANION_SCHEMA).validate(COMPANION_EVENT | {"body": "a" * 3001})


def test_watch_event_with_short_body_is_not_truncated() -> None:
    validator(WATCH_SCHEMA).validate(WATCH_EVENT | {"body": "Привет", "body_truncated": False})
