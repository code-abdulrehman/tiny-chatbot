"""Stable gateway error codes, exception type, and the public error envelope."""

from fastapi import Request
from fastapi.responses import JSONResponse
from uuid import uuid4

# Stable error codes from docs/model-gateway-architecture.md section 6.
GATEWAY_ERROR_STATUS = {
    "invalid_request": 400,
    "unsupported_capability": 400,
    "context_limit_exceeded": 400,
    "model_not_found": 404,
    "payload_too_large": 413,
    "unauthenticated": 401,
    "forbidden": 403,
    "key_revoked": 401,
    "key_expired": 401,
    "account_suspended": 403,
    "idempotency_conflict": 409,
    "deployment_changed": 409,
    "quota_exceeded": 429,
    "rate_limited": 429,
    "concurrency_limit": 429,
    "model_error": 502,
    "model_unavailable": 503,
    "model_timeout": 504,
}

DEFAULT_ERROR_STATUS = 500


class GatewayError(Exception):
    """An error that maps onto one of the stable gateway error codes."""

    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    @property
    def status_code(self):
        return GATEWAY_ERROR_STATUS.get(self.code, DEFAULT_ERROR_STATUS)

    @property
    def error(self):
        payload = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


def error_body(code, message, request_id=None, details=None):
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error, "request_id": request_id}


def gateway_error_response(code, message, request_id=None, details=None, status_code=None):
    status = status_code or GATEWAY_ERROR_STATUS.get(code, DEFAULT_ERROR_STATUS)
    return JSONResponse(status_code=status, content=error_body(code, message, request_id, details))


def invalid_request(message, details=None):
    return GatewayError("invalid_request", message, details)


def unauthenticated(message="Authentication is required."):
    return GatewayError("unauthenticated", message)


def forbidden(message="The principal is not allowed to perform this action."):
    return GatewayError("forbidden", message)


def key_revoked(message="This API key has been revoked."):
    return GatewayError("key_revoked", message)


def key_expired(message="This API key has expired."):
    return GatewayError("key_expired", message)


def account_suspended(message="This account is suspended."):
    return GatewayError("account_suspended", message)


def context_limit_exceeded(message="The request exceeds the model context window.", details=None):
    return GatewayError("context_limit_exceeded", message, details)


def quota_exceeded(message="The quota for this principal is exhausted.", details=None):
    return GatewayError("quota_exceeded", message, details)


async def gateway_error_handler(request: Request, exc: GatewayError):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    return gateway_error_response(
        exc.code, exc.message, request_id=request_id, details=exc.details, status_code=exc.status_code
    )
