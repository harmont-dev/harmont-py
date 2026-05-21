"""Abstract Deployment + LocalDeployment construction tests."""
from __future__ import annotations

import pytest

from harmont._deploy import Deployment


def test_deployment_is_abstract_dataclass():
    """Deployment carries name + driver, is frozen, and is constructible (sentinel-level)."""
    d = Deployment(name="db", driver="local")
    assert d.name == "db"
    assert d.driver == "local"
    with pytest.raises(Exception):
        d.name = "other"  # type: ignore[misc]  # frozen
