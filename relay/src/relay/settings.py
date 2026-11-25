"""Relay configuration from environment variables (template: the repo-root .env.example)."""

from pathlib import Path

from pydantic import DirectoryPath, PositiveInt, SecretStr, field_validator
from pydantic_settings import BaseSettings

# The repo-root protocol/ directory, next to relay/ in a source checkout.
SOURCE_PROTOCOL_DIR = Path(__file__).resolve().parents[3] / "protocol"


class RelaySettings(BaseSettings):
    """Everything the HTTP app needs besides the APNs credentials (ApnsSettings)."""

    database_url: str = "sqlite+aiosqlite:///data/relay.db"
    # Until pairing (M2), one static bearer token authenticates the Companion,
    # and the watch push token is configured by hand.
    relay_token: SecretStr
    watch_push_token: str
    retention_days: PositiveInt = 7
    # JSON schemas the relay validates request bodies against.
    protocol_dir: DirectoryPath = SOURCE_PROTOCOL_DIR

    @field_validator("watch_push_token")
    @classmethod
    def join_token_groups(cls, token: str) -> str:
        """The watch app shows the token in groups; they may be pasted with the spaces."""
        return "".join(token.split())
