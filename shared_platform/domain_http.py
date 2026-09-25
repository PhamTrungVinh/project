"""Small authenticated HTTP client for optional extracted-domain adapters."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from fastapi import HTTPException

from config import DOMAIN_SERVICE_TIMEOUT_SECONDS
from logger import agent_logger, request_id_context


def request_json(
    base_url: str,
    method: str,
    path: str,
    token: str,
    payload: dict | None = None,
    query: dict | None = None,
    idempotency_key: str | None = None,
) -> dict | list:
    """Call a private domain API while preserving caller identity and errors."""
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{urlencode(query)}"

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    correlation_id = request_id_context.get()
    if correlation_id:
        headers["X-Request-ID"] = correlation_id
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    status_code = None
    error_type = None
    try:
        with urlopen(request, timeout=DOMAIN_SERVICE_TIMEOUT_SECONDS) as response:
            status_code = getattr(response, "status", 200)
            raw_body = response.read().decode("utf-8")
        return json.loads(raw_body)
    except HTTPError as exc:
        status_code = exc.code
        error_type = "HTTPError"
        raw_body = exc.read().decode("utf-8")
        try:
            detail = json.loads(raw_body).get("detail", raw_body)
        except json.JSONDecodeError:
            detail = raw_body or "Domain service request failed"
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except URLError as exc:
        error_type = "URLError"
        raise HTTPException(status_code=503, detail="Domain service is unavailable") from exc
    except TimeoutError:
        error_type = "TimeoutError"
        raise
    except json.JSONDecodeError as exc:
        error_type = "InvalidJSON"
        raise HTTPException(status_code=502, detail="Domain service returned invalid JSON") from exc
    finally:
        agent_logger.info(
            "service_call target=%s method=%s status=%s duration_ms=%s result=%s",
            urlsplit(base_url).hostname, method, status_code,
            round((time.monotonic() - started) * 1000),
            "error" if error_type else "ok",
        )
