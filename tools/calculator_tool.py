from typing import Annotated
import numexpr
from langchain.tools import tool
from langgraph.prebuilt import InjectedState

from state import AgentState


@tool
def calculator_tool(
    expression: str,
) -> str:
    """Useful for performing mathematical calculations.
    Input should be a valid Python mathematical expression."""
    try:
        result = numexpr.evaluate(expression).item()
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"
