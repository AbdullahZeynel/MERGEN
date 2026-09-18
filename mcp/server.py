"""Private VPS demo tools. No model inference and no write tools."""
import os
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from demo_store import DemoStore, PATHOLOGY_IMAGES

store = DemoStore(os.environ['MERGEN_DEMO_ROOT'])
server = FastMCP('MERGEN demo', host='127.0.0.1', port=9010,
                 stateless_http=True, json_response=True,
                 transport_security=TransportSecuritySettings(
                     enable_dns_rebinding_protection=True,
                     allowed_hosts=['127.0.0.1:9010', 'localhost:9010'], allowed_origins=[]))


@server.tool()
def list_catalog() -> dict[str, Any]:
    """List available demo modules and diseases without exposing disk paths."""
    return store.catalog()


@server.tool()
def list_cases(module: str = 'imaging', disease: str = 'glioma') -> dict[str, Any]:
    """List one prepared demo collection; never substitutes live results."""
    return store.list_cases(module, disease)


@server.tool()
def get_slice(case_id: str, axis: str, index: int, module: str = 'imaging',
              disease: str = 'glioma') -> dict[str, Any]:
    """Read a zero-based slice from a listed case and axis."""
    return store.asset(case_id, 'slice', axis, index, module=module, disease=disease)


@server.tool()
def get_overlay(case_id: str, layer: str, axis: str, index: int,
                module: str = 'imaging', disease: str = 'glioma') -> dict[str, Any]:
    """Read a transparent prediction or ground-truth mask for a demo slice."""
    return store.asset(case_id, 'overlay', axis, index, layer=layer,
                       module=module, disease=disease)


@server.tool()
def get_mesh(case_id: str, module: str = 'imaging', disease: str = 'glioma') -> dict[str, Any]:
    """Read tumor surfaces and approximate MR foreground envelope."""
    return store.asset(case_id, 'mesh', module=module, disease=disease)


@server.tool()
def get_pathology_image(case_id: str, kind: str, module: str = 'pathology',
                        disease: str = 'glioma') -> dict[str, Any]:
    """Read the attention map, top tiles or slide thumbnail of a listed case."""
    if kind not in PATHOLOGY_IMAGES:
        return {'error': 'invalid'}
    return store.asset(case_id, kind, module=module, disease=disease)


@server.tool()
def get_case_report(case_id: str, module: str = 'pathology',
                    disease: str = 'glioma') -> dict[str, Any]:
    """Read the prepared per-case report; carries no disk path or live result."""
    return store.asset(case_id, 'report', module=module, disease=disease)


@server.tool()
def get_example_figure(example_id: str, module: str = 'imaging',
                       disease: str = 'glioma') -> dict[str, Any]:
    """Read a validation figure measured elsewhere; not a browsable case."""
    return store.example(example_id, module=module, disease=disease)


if __name__ == '__main__':
    server.run(transport='streamable-http')
