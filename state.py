from typing import TypedDict, NotRequired, List, Annotated
from langgraph.graph import add_messages
from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]

    # Routing
    route: NotRequired[str]
    hop_count: NotRequired[int]
    agent_responses: NotRequired[list[str]]
    unfinished_tasks: NotRequired[list[dict]]  # queued tasks waiting for user input, with a TTL

    # Context: user_name holds str(owner_id), not a user-supplied display name
    user_name: NotRequired[str]
    user_email: NotRequired[str]
    thread_id: NotRequired[str]
    current_datetime: NotRequired[str]

    # Memory
    retrieved_memory: NotRequired[str]

    # Guardrail
    blocked: NotRequired[bool]
    block_reason: NotRequired[str]