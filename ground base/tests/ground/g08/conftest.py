"""Keep process-wide adapter ownership isolated between tests."""

from __future__ import annotations

import pytest
from patrol.ground.extensions.g08.gateway import clear_claims_for_tests


@pytest.fixture(autouse=True)
def _clear_adapter_owners() -> object:
    clear_claims_for_tests()
    yield
    clear_claims_for_tests()
