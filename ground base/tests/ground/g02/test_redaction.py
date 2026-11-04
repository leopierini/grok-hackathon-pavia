"""Redaction keeps synthetic credentials out of errors and journals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from patrol.ground.extensions.g02.loading import canonical_settings
from patrol.ground.kernel.faults import GroundFault
from tests.ground.g02.support import FAKE, service, write_json, write_text

_SECRET = "synthetic-secret-value"


def test_redacted_view_and_errors_omit_the_secret(tmp_path: Path) -> None:
    write_json(
        tmp_path / "grok.json",
        {
            "model": "configured-model",
            "prompt_version": "v1",
            "request_timeout_s": 20,
            "api_key": _SECRET,
        },
    )
    ground = tmp_path / "ground.json"
    write_json(ground, {"grok_config_path": "grok.json", "zones": ["room_2"]})
    before = hashlib.sha256(ground.read_bytes()).hexdigest()
    port = service(tmp_path)
    settings = port.load(ground, modes=FAKE, scenario=None)
    view = port.redacted(settings)
    encoded = json.dumps(dict(view), sort_keys=True, default=str)
    assert view["adapter_configs"] == "redacted"
    assert _SECRET not in encoded
    assert _SECRET in canonical_settings(settings)
    assert hashlib.sha256(ground.read_bytes()).hexdigest() == before
    assert list(tmp_path.rglob("*.partial")) == []
    with pytest.raises(TypeError):
        view["scenario"] = "dismiss"  # type: ignore[index]


def test_exception_does_not_echo_a_secret_value(tmp_path: Path) -> None:
    write_text(
        tmp_path / "ground.json",
        '{"zones": ["room_2"], "api_key": "' + _SECRET + '", "arrival_timeout_s": true}',
    )
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=FAKE, scenario=None)
    assert caught.value.error.code == "invalid_input"
    assert _SECRET not in caught.value.error.detail
    assert _SECRET not in str(caught.value)


def test_profile_identity_cannot_carry_a_credential(tmp_path: Path) -> None:
    write_json(tmp_path / "grok.json", {"api_key": _SECRET})
    write_json(
        tmp_path / "ground.json",
        {
            "zones": ["room_2"],
            "grok_config_path": "grok.json",
            "profile_identity": _SECRET,
        },
    )
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=FAKE, scenario=None)
    assert "credential" in caught.value.error.detail
    assert _SECRET not in str(caught.value)
