from typing import TypedDict, NotRequired, List, Annotated
from langgraph.graph import add_messages
from langchain.messages import AnyMessage


class AgentState(TypedDict):
    """State used by all nodes in the multi-agent graph."""
    messages: Annotated[List[AnyMessage], add_messages]

    # Routing
    route: NotRequired[str]

    # User context is automatically injected into every tool call when available.
    user_name: NotRequired[str]
    user_email: NotRequired[str]      # Optional, can be set at startup or automatically detected by the `context_node`.

    current_datetime: NotRequired[str]

    preferences: NotRequired[dict]

    # RAG results
    context: NotRequired[str]
    sources: NotRequired[List[str]]

    # Guardrail results
    blocked: NotRequired[bool]
    block_reason: NotRequired[str]

    #semantic + episodic facts
    retrieved_memory: NotRequired[str] 

    pending_intent: NotRequired[str]
    thread_id: NotRequired[str]

    hop_count: NotRequired[int]
    agent_responses: NotRequired[list[str]]
    unfinished_tasks: NotRequired[list[dict]]
