"""Relay configuration from environment variables (template: the repo-root .env.example)."""

from pathlib import Path
from typing import Annotated

from pydantic import DirectoryPath, Field, PositiveInt, SecretStr, field_validator
from pydantic_settings import BaseSettings

# The repo-root protocol/ directory, next to relay/ in a source checkout.
SOURCE_PROTOCOL_DIR = Path(__file__).resolve().parents[3] / "protocol"


class RelaySettings(BaseSettings):
    """Everything the HTTP app needs besides the APNs credentials (ApnsSettings)."""

    database_url: str = "sqlite+aiosqlite:///data/relay.db"
    # Shared with the watch build: only the owner's watch may start pairing (§5.2).
    pairing_secret: Annotated[SecretStr, Field(min_length=32)]
    # How long a pairing code works (§5.2).
    pairing_ttl_seconds: PositiveInt = 600
    retention_days: PositiveInt = 7
    # JSON schemas the relay validates request bodies against.
    protocol_dir: DirectoryPath = SOURCE_PROTOCOL_DIR

    @field_validator("pairing_secret")
    @classmethod
    def secret_fits_a_header(cls, secret: SecretStr) -> SecretStr:
        """Rejects a secret the watch could not send intact in `Authorization: Bearer`."""
        if not all("!" <= char <= "~" for char in secret.get_secret_value()):
            raise ValueError("use printable ASCII without spaces, e.g. openssl rand -base64 32")
        return secret
