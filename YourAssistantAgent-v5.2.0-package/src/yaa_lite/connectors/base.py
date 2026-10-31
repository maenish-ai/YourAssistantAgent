from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ConnectorStatus:
    name: str
    connected: bool
    detail: str = ""

class Connector:
    name = "Connector"
    def status(self) -> ConnectorStatus:
        return ConnectorStatus(self.name, False, "Not configured")
