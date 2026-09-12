"""Private VPS demo tools. No model inference and no write tools."""
import os
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from demo_store import DemoStore

store = DemoStore(os.environ['MERGEN_DEMO_ROOT'])
server = FastMCP('MERGEN demo', host='127.0.0.1', port=9010,
                 stateless_http=True, json_response=True,
                 transport_security=TransportSecuritySettings(
                     enable_dns_rebinding_protection=True,
                     allowed_hosts=['127.0.0.1:9010', 'localhost:9010'], allowed_origins=[]))


@server.tool()
def list_cases() -> dict[str, Any]:
    """List prepared demo cases; never substitutes live results."""
    return store.manifest


@server.tool()
def get_slice(case_id: str, axis: str, index: int) -> dict[str, Any]:
    """Read a zero-based slice from a listed case and axis."""
    return store.asset(case_id, 'slice', axis, index)


@server.tool()
def get_mesh(case_id: str) -> dict[str, Any]:
    """Read tumor surfaces and approximate MR foreground envelope."""
    return store.asset(case_id, 'mesh')


if __name__ == '__main__':
    server.run(transport='streamable-http')
