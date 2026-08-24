import time
from groq import BadRequestError
from logger import agent_logger


def invoke_with_retry(llm_with_tools, messages, max_retries: int = 2):
    """Invoke an LLM with tool calling, automatically retrying if the model
    generates an invalid function call syntax (a common tool_use_failed error
    with open-weight models on Groq when many tools are bound)."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return llm_with_tools.invoke(messages)
        except BadRequestError as e:
            last_error = e
            agent_logger.warning(
                f"LLM tool_use_failed, attempt {attempt + 1}/{max_retries + 1}: {e}"
            )
            time.sleep(0.5)

    # All retries failed -> return an AIMessage with an error instead of crashing the entire app
    from langchain_core.messages import AIMessage
    agent_logger.error(
        f"LLM tool_use_failed after {max_retries + 1} attempts, giving up"
    )
    return AIMessage(
        content="Sorry, I encountered an issue while processing this request. Please try rephrasing your question."
    )