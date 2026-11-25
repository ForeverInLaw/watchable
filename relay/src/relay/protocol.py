"""The JSON contract in the repo-root protocol/ directory (see protocol/README.md)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_validator(protocol_dir: Path, schema_file: str) -> Draft202012Validator:
    """Validator for `protocol_dir/schema/<schema_file>`, with format checks on.

    Schemas reference each other by file name, so all of them are loaded.
    """
    registry: Registry[Any] = Registry().with_resources(
        (path.name, Resource.from_contents(load_json(path)))
        for path in (protocol_dir / "schema").glob("*.schema.json")
    )
    return Draft202012Validator(
        {"$ref": schema_file},
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


class InvalidBody(ValueError):
    """The body breaks the schema. The message names the rule, never the offending value."""


class BodyParser[T]:
    """Checks request bodies against one schema in protocol/ and types them as `T`.

    `T` is the TypedDict the schema describes, e.g. BodyParser[NotificationEvent].
    """

    def __init__(self, protocol_dir: Path, schema_file: str) -> None:
        self._validator = schema_validator(protocol_dir, schema_file)

    def parse(self, body: object) -> T:
        error = next(self._validator.iter_errors(body), None)
        if error is not None:
            raise InvalidBody(f"{error.json_path} fails {error.validator}")
        # JSON escapes can carry a lone surrogate, which neither SQLite nor APNs accepts.
        try:
            json.dumps(body, ensure_ascii=False).encode()
        except UnicodeEncodeError as encode_error:
            raise InvalidBody("$ has text that is not valid Unicode") from encode_error
        # The schema has just proven the shape the TypedDict describes.
        return cast(T, body)


def rfc3339(moment: datetime) -> str:
    """The protocol's timestamp form: RFC3339 UTC with a Z suffix, to the second."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
