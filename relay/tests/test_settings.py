"""Relay settings that would leave the relay unusable are refused at startup."""

import pytest
from pydantic import ValidationError

from relay.settings import RelaySettings


@pytest.mark.parametrize(
    "secret",
    ["a" * 31, " " * 32, "a" * 31 + " ", "ж" * 32],
    ids=["too short", "spaces", "trailing space", "not ascii"],
)
def test_pairing_secret_a_header_cannot_carry_is_refused(secret: str) -> None:
    with pytest.raises(ValidationError, match="pairing_secret"):
        RelaySettings(pairing_secret=secret)
