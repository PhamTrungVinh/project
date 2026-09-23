"""Small authenticated HTTP client for optional extracted-domain adapters."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException

from config import DOMAIN_SERVICE_TIMEOUT_SECONDS


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
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=DOMAIN_SERVICE_TIMEOUT_SECONDS) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8")
        try:
            detail = json.loads(raw_body).get("detail", raw_body)
        except json.JSONDecodeError:
            detail = raw_body or "Domain service request failed"
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except URLError as exc:
        raise HTTPException(status_code=503, detail="Domain service is unavailable") from exc

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Domain service returned invalid JSON") from exc
