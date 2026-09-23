from logger import request_id_context

def correlation_id() -> str | None:
    return request_id_context.get(None)
