"""Correlation-ID middleware shared by extracted services."""

import re
import uuid

from fastapi import Request

from logger import request_id_context


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


async def request_context_middleware(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid.uuid4().hex
    request.state.correlation_id = request_id
    token = request_id_context.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_context.reset(token)
