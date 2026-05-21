"""harmont.dev — local Docker deployment driver.

Public surface (grows across tasks):

    deploy(*, image=None, from_=None, cmd=None,
           port_mapping=None, env=None,
           volumes=None, workdir=None) -> LocalDeployment
    port()                                  -> _PortSentinel
    LocalDeployment                          (concrete subclass)
    dump_registry_json()                    -> str  (Task 8)
"""
from __future__ import annotations

from ._deployment import LocalDeployment
from ._factory import deploy
from ._port import port

__all__ = ["LocalDeployment", "deploy", "port"]
