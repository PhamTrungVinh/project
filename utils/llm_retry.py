import re
import time

from groq import BadRequestError, RateLimitError
from langchain_core.messages import AIMessage

from logger import agent_logger

RATE_LIMIT_MESSAGE = (
    "The assistant is temporarily busy due to an AI provider rate limit. "
    "Please try again in a few seconds."
)


def _rate_limit_delay(error: Exception, attempt: int) -> float:
    """Use Retry-After when available, otherwise use the provider hint/backoff."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after:
        try:
            return min(max(float(retry_after), 0.1), 10.0)
        except ValueError:
            pass

    hint = re.search(r"try again in\s+([0-9.]+)s", str(error), re.IGNORECASE)
    if hint:
        return min(max(float(hint.group(1)), 0.1), 10.0)
    return min(0.5 * (2 ** attempt), 5.0)


def invoke_with_retry(llm_with_tools, messages, max_retries: int = 2):
    """Invoke a tool-enabled LLM with bounded retries and a safe fallback."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return llm_with_tools.invoke(messages)
        except RateLimitError as error:
            last_error = error
            if attempt < max_retries:
                delay = _rate_limit_delay(error, attempt)
                agent_logger.warning(
                    "llm_rate_limited attempt=%s/%s retry_in_seconds=%.2f",
                    attempt + 1,
                    max_retries + 1,
                    delay,
                )
                time.sleep(delay)
                continue
            agent_logger.warning(
                "llm_rate_limited_exhausted attempts=%s", max_retries + 1
            )
        except BadRequestError as error:
            last_error = error
            agent_logger.warning(
                "llm_tool_call_failed attempt=%s/%s error=%s",
                attempt + 1,
                max_retries + 1,
                error,
            )
            if attempt < max_retries:
                time.sleep(0.5)
                continue

        break

    agent_logger.error(
        "llm_invocation_failed attempts=%s error_type=%s",
        max_retries + 1,
        type(last_error).__name__ if last_error else "unknown",
    )
    message = RATE_LIMIT_MESSAGE if isinstance(last_error, RateLimitError) else (
        "Sorry, I encountered an issue while processing this request. "
        "Please try rephrasing your question."
    )
    return AIMessage(content=message)
