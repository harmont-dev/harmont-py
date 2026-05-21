"""harmont.dev — local Docker deployment driver.

Public surface (grows across tasks):

    deploy(*, image=None, from_=None, cmd=None,
           port_mapping=None, env=None,
           volumes=None, workdir=None) -> LocalDeployment
    port()                                  -> _PortSentinel
    LocalDeployment                          (concrete subclass)
    dump_registry_json()                    -> str
"""
from __future__ import annotations

from ._port import _PortSentinel, port

__all__ = ["_PortSentinel", "port"]
