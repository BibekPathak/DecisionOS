"""HTTP middleware.

Attaches a request id (and the active trace id) to every request, records
request latency, and echoes the request id back on the response. The decision
id is added to the context later, inside the engine.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from decisionos.observability.context import request_context
from decisionos.observability.metrics import observe_http_request
from decisionos.observability.tracing import current_trace_id

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Establishes a request-scoped context and records latency."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id
        started = time.perf_counter()

        with request_context(request_id=request_id, trace_id=current_trace_id()):
            response = await call_next(request)

        elapsed = time.perf_counter() - started
        route = _route_template(request)
        # Metrics must never break a request, so failures here are suppressed.
        with contextlib.suppress(Exception):
            observe_http_request(
                method=request.method,
                route=route,
                status=response.status_code,
                latency_seconds=elapsed,
            )

        response.headers[_REQUEST_ID_HEADER] = request_id
        return response


def _route_template(request: Request) -> str:
    """Return the matched route template, falling back to the raw path."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else request.url.path


__all__ = ["RequestContextMiddleware"]
