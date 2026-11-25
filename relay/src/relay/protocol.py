"""The JSON contract in the repo-root protocol/ directory (see protocol/README.md)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


def rfc3339(moment: datetime) -> str:
    """The protocol's timestamp form: RFC3339 UTC with a Z suffix, to the second."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
