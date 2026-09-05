import logging

from logger import JsonFormatter, request_id_context


def test_json_formatter_includes_router_request_and_route():
    record = logging.LogRecord("agent", logging.INFO, __file__, 1, "router_selected_route", (), None)
    record.user_request = "How do I book a room?"
    record.route = "booking"
    token = request_id_context.set("request-123")
    try:
        rendered = JsonFormatter().format(record)
    finally:
        request_id_context.reset(token)

    assert '"user_request": "How do I book a room?"' in rendered
    assert '"route": "booking"' in rendered
    assert '"request_id": "request-123"' in rendered
