"""SDK error taxonomy.

Errors map cleanly onto HTTP status codes so callers can branch on the class
rather than parsing messages.
"""

from __future__ import annotations

from typing import Any


class DecisionOSError(Exception):
    """Base class for all SDK errors."""


class DecisionOSConnectionError(DecisionOSError):
    """The server could not be reached, or the request timed out."""


class DecisionOSAPIError(DecisionOSError):
    """The server returned an unsuccessful response.

    Attributes
    ----------
    status_code:
        The HTTP status code.
    detail:
        The server's error detail, when present.
    body:
        The decoded response body, when it was JSON.
    request_id:
        The ``X-Request-ID`` echoed by the server, when present.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        detail: str | None = None,
        body: Any = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        self.body = body
        self.request_id = request_id


class BadRequestError(DecisionOSAPIError):
    """The request was invalid (400/422)."""


class AuthenticationError(DecisionOSAPIError):
    """Authentication failed or is missing (401/403)."""


class NotFoundError(DecisionOSAPIError):
    """The requested resource does not exist (404)."""


class ConflictError(DecisionOSAPIError):
    """The request conflicts with existing state (409)."""


class RateLimitError(DecisionOSAPIError):
    """The server rate-limited the request (429)."""

    def __init__(self, *args: Any, retry_after: float | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


class ServerError(DecisionOSAPIError):
    """The server failed to process the request (5xx)."""


_STATUS_TO_ERROR: dict[int, type[DecisionOSAPIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: AuthenticationError,
    404: NotFoundError,
    409: ConflictError,
    422: BadRequestError,
    429: RateLimitError,
}


def error_for_status(
    status_code: int,
    *,
    detail: str | None = None,
    body: Any = None,
    request_id: str | None = None,
) -> DecisionOSAPIError:
    """Build the appropriate error for an HTTP status code."""
    error_type = _STATUS_TO_ERROR.get(status_code)
    if error_type is None:
        error_type = ServerError if status_code >= 500 else DecisionOSAPIError
    message = detail or f"request failed with status {status_code}"
    if error_type is RateLimitError:
        return RateLimitError(
            message,
            status_code=status_code,
            detail=detail,
            body=body,
            request_id=request_id,
        )
    return error_type(
        message,
        status_code=status_code,
        detail=detail,
        body=body,
        request_id=request_id,
    )


__all__ = [
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "DecisionOSAPIError",
    "DecisionOSConnectionError",
    "DecisionOSError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "error_for_status",
]
