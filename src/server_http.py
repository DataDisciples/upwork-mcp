"""HTTP wrapper: exposes /health alongside the FastMCP app.

Same shape as utilities/teamwork-mcp/src/server_http.py.
"""

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route


def _get_mcp_asgi_app(mcp: FastMCP):
    for attr in ("http_app", "streamable_http_app", "sse_app"):
        method = getattr(mcp, attr, None)
        if callable(method):
            return method()
    raise RuntimeError(
        "FastMCP exposes no HTTP transport method "
        "(tried http_app, streamable_http_app, sse_app)."
    )


def build_http_app(mcp: FastMCP):
    mcp_app = _get_mcp_asgi_app(mcp)

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": mcp.name})

    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/", app=mcp_app),
        ],
        lifespan=getattr(mcp_app, "lifespan", None),
    )
