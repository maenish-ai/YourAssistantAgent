from .base import Connector, ConnectorStatus

class FacebookConnector(Connector):
    name = "Facebook"
    def status(self) -> ConnectorStatus:
        # The lightweight shell never opens a browser at startup. A future connector
        # module can provide discovery/publishing in its own worker process.
        return ConnectorStatus(self.name, False, "Connect from Settings when needed")
