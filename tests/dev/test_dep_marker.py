"""hm.Dep[T] marker is detected; call_with_deps resolves it from DEPLOYMENTS."""
from __future__ import annotations

import pytest

from harmont import Dep
from harmont._deploy import DEPLOYMENTS, Deployment
from harmont._deps import call_with_deps


def test_dep_marker_alias_subscripts_to_annotated():
    # Dep is PEP-593 Annotated[T, _DEP_MARKER]; subscripting works at
    # both static and runtime levels.
    from typing import get_args, get_origin

    T = Dep[Deployment]
    assert get_origin(T) is not None
    args = get_args(T)
    assert args[0] is Deployment


def test_call_with_deps_resolves_dep_param_from_DEPLOYMENTS():
    # Register a fake deployment under the name "db".
    DEPLOYMENTS["db"] = lambda: Deployment(name="db", driver="local")

    def consumer(db: Dep[Deployment]) -> Deployment:
        return db

    result = call_with_deps(consumer)
    assert isinstance(result, Deployment)
    assert result.name == "db"


def test_call_with_deps_raises_when_dep_unknown():
    def consumer(redis: Dep[Deployment]) -> Deployment:
        return redis

    with pytest.raises(ValueError, match="hm.Dep parameter 'redis' refers to"):
        call_with_deps(consumer)
