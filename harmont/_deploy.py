"""Driver-agnostic deployment registry, decorator, and Dep marker.

This module is intentionally driver-free. Concrete deployment types
(``LocalDeployment``, future ``AwsDeployment``, …) live in their own
driver subpackages (``harmont.dev``, future ``harmont.aws``).
The registry stores deployments polymorphically; CLI subcommands filter
by ``isinstance`` or by the ``driver`` discriminator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class Deployment:
    """Abstract deployment record. Subclassed per driver.

    ``name`` is the slug the user passed to ``@hm.deploy``.
    ``driver`` is the discriminator string ("local" for ``hm.dev``).
    """
    name: str
    driver: str


# Registry: slug -> zero-arg callable that re-invokes the user-defined
# function with deps resolved. Same shape as REGISTRATIONS for pipelines.
DEPLOYMENTS: dict[str, Callable[[], Deployment]] = {}
