"""Model gateway HTTP API."""

from uuid import uuid4
import json

from typing import Optional

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from gateway import adapters as adapter_module
from gateway import auth as auth_module
from gateway import config, errors, quota, router as router_module
from gateway.errors import GatewayError, gateway_error_handler
from gateway.auth import Principal


class Message(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str = Field(..., min_length=1)


class ChatCompletionRequest(BaseModel):
    model: str = Field(..., min_length=1)
    messages: list[Message] = Field(..., min_length=1, max_length=40)
    max_output_tokens: int = Field(0, ge=1)
    stream: bool = False


def create_app(key_store, dev_api_key: str = "", router=None) -> FastAPI:
    app = FastAPI(title="Model Gateway", version="0.1.0", description="Reusable API for a model hosted on one device.")

    app.add_exception_handler(GatewayError, gateway_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": "The request body failed validation.", "details": {"errors": exc.errors()}}, "request_id": request_id},
        )

    app.state.key_store = key_store
    app.state.dev_api_key = dev_api_key
    app.state.router = router if router is not None else router_module.Router()
    app.state.quota = quota.QuotaLedger()

    def get_principal(authorization: str = Header(default="")) -> Principal:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() != "bearer" or not credentials.strip():
            raise errors.unauthenticated("Authentication is required.")
        return auth_module.resolve_principal(credentials.strip(), key_store, dev_api_key)

    def resolve_adapter(model: str):
        return app.state.router.resolve(model)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    def chat_completions(body: ChatCompletionRequest, request: Request, principal: Principal = Depends(get_principal)):
        if principal.state != "active":
            raise errors.account_suspended("This account is suspended.")
        if auth_module.INFERENCE_CHAT not in principal.scopes:
            raise errors.forbidden("The principal lacks the inference:chat scope.")

        adapter = resolve_adapter(body.model)
        deployment = adapter.describe()
        if adapter_module.CHAT not in deployment.capabilities:
            raise errors.GatewayError("unsupported_capability", f"Model {body.model} does not support chat.", {"model": body.model})

        max_output_tokens = body.max_output_tokens or config.MAX_OUTPUT_TOKENS
        input_tokens = adapter.count_input([m.model_dump() for m in body.messages])
        if input_tokens + max_output_tokens > deployment.context_window:
            raise errors.context_limit_exceeded(
                f"The request needs about {input_tokens} input tokens plus a {max_output_tokens} token reply; the context window is {deployment.context_window}.",
                {"input_tokens": input_tokens, "max_output_tokens": max_output_tokens, "context_window": deployment.context_window},
            )

        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        reservation_cost = quota.credit_cost(input_tokens, max_output_tokens, input_weight=1.0, output_weight=2.0)
        decision = app.state.quota.reserve(reservation_cost, quota.Limits(rolling_credits=config.FREE_CREDITS))
        if not decision.allowed:
            raise errors.quota_exceeded("The quota for this principal is exhausted.", {"reserved_credits": decision.reserved_credits, "reasons": list(decision.reasons)})

        result = adapter.generate(
            adapter_module.GenerateRequest(model=body.model, messages=[m.model_dump() for m in body.messages], max_output_tokens=max_output_tokens, stream=body.stream),
        )
        events = list(result)
        final = events[-1]
        usage = adapter.normalize_usage(final)
        app.state.quota.settle(reservation_cost)
        decision = app.state.quota.evaluate(0, quota.Limits(rolling_credits=config.FREE_CREDITS))

        content = final.get("content") or ""
        response = {
            "id": request_id,
            "model": f"{deployment.model}@{deployment.version}",
            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": final.get("finish_reason") or "stop"}],
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.input_tokens + usage.output_tokens,
                "credits": quota.credit_cost(input_tokens, usage.output_tokens, input_weight=1.0, output_weight=2.0),
                "source": usage.source,
            },
            "quota": {"remaining_5h_credits": decision.remaining_by_window.get("rolling"), "reserved_credits": app.state.quota.reserved_credits},
        }

        if not body.stream:
            return response

        def sse():
            yield f"event: done\ndata: {json.dumps(response)}\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    @app.get("/v1/models")
    def models(principal=Depends(get_principal)):
        return {"object": "list", "data": app.state.router.deployments()}

    return app

