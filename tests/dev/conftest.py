"""Per-test reset of every registry the deploy DSL touches."""
from __future__ import annotations

import pytest

from harmont._deploy import DEPLOYMENTS
from harmont._deps import _TARGETS_BY_NAME, _RESOLVING
from harmont._registry import REGISTRATIONS


@pytest.fixture(autouse=True)
def _reset_registries():
    """Clear every module-level registry before each test so order is irrelevant."""
    DEPLOYMENTS.clear()
    _TARGETS_BY_NAME.clear()
    _RESOLVING.clear()
    REGISTRATIONS.clear()
    yield
    DEPLOYMENTS.clear()
    _TARGETS_BY_NAME.clear()
    _RESOLVING.clear()
    REGISTRATIONS.clear()
