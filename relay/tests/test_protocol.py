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


COMPANION_EVENT = load(PROTOCOL / "examples" / "notification-event.json")


@pytest.mark.parametrize(
    "event",
    [
        COMPANION_EVENT | {"posted_at": "2026-11-24T15:00:00+03:00"},
        COMPANION_EVENT | {"event_id": "018f"},
        {key: value for key, value in COMPANION_EVENT.items() if key != "notification_key"},
        COMPANION_EVENT | {"body_truncated": False},
    ],
    ids=["posted_at not in UTC", "event_id not a UUID", "no notification_key", "unknown field"],
)
def test_companion_event_rejects(event: dict[str, Any]) -> None:
    assert not validator("notification-event.schema.json").is_valid(event)


def test_companion_event_carries_the_full_body() -> None:
    event = COMPANION_EVENT | {"body": "a" * 3001}

    validator("notification-event.schema.json").validate(event)


WATCH_EVENT = load(PROTOCOL / "examples" / "notification-event-watch.truncated.json")


@pytest.mark.parametrize(
    "event",
    [
        WATCH_EVENT | {"body": "a" * 3001},
        WATCH_EVENT | {"body": "Привет"},
        WATCH_EVENT | {"body": None},
        {key: value for key, value in WATCH_EVENT.items() if key != "body_truncated"},
        WATCH_EVENT | {"body_full": "a" * 3001},
    ],
    ids=[
        "body over 3000",
        "truncated body under 3000",
        "truncated null body",
        "no body_truncated",
        "unknown field",
    ],
)
def test_watch_event_rejects(event: dict[str, Any]) -> None:
    assert not validator("notification-event-watch.schema.json").is_valid(event)


def test_watch_event_with_short_body_is_not_truncated() -> None:
    event = WATCH_EVENT | {"body": "Привет", "body_truncated": False}

    validator("notification-event-watch.schema.json").validate(event)
