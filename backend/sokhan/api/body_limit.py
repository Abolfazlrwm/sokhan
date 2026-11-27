from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MULTIPART_OVERHEAD_BYTES = 1024 * 1024

_DETAIL = "request body too large"
_PAYLOAD_TOO_LARGE = 413


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_body_bytes:
            response = JSONResponse(
                {"detail": _DETAIL}, status_code=_PAYLOAD_TOO_LARGE
            )
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise HTTPException(_PAYLOAD_TOO_LARGE, _DETAIL)
            return message

        await self.app(scope, limited_receive, send)
