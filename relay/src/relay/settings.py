"""Relay configuration from environment variables (template: the repo-root .env.example)."""

from pathlib import Path

from pydantic import DirectoryPath, PositiveInt
from pydantic_settings import BaseSettings

# The repo-root protocol/ directory, next to relay/ in a source checkout.
SOURCE_PROTOCOL_DIR = Path(__file__).resolve().parents[3] / "protocol"


class RelaySettings(BaseSettings):
    """Everything the HTTP app needs besides the APNs credentials (ApnsSettings)."""

    database_url: str = "sqlite+aiosqlite:///data/relay.db"
    # How long a pairing code works (§5.2).
    pairing_ttl_seconds: PositiveInt = 600
    retention_days: PositiveInt = 7
    # JSON schemas the relay validates request bodies against.
    protocol_dir: DirectoryPath = SOURCE_PROTOCOL_DIR
