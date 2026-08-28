from typing import Annotated
from cachetools import TTLCache
from langchain.tools import tool
from langchain_tavily import TavilySearch
from langgraph.prebuilt import InjectedState

from config import TAVILY_API_KEY
from state import AgentState

_cache = TTLCache(maxsize=100, ttl=3600)

_search_tool = TavilySearch(
    max_results=5,
    search_depth="advanced",
    include_answer=True,
    include_raw_content=False,
)

def _get_search_tool():
    global _search_tool
    if _search_tool is None:
        from langchain_tavily import TavilySearch
        _search_tool = TavilySearch(max_results=5, search_depth="advanced", include_answer=True)
    return _search_tool

@tool
def search_with_cache(
    query: str,
    state: Annotated[AgentState, InjectedState],
) -> str:
    """Search the web for current information using Tavily API with caching.
    Best used for: recent news, current events, factual information.
    Input should be a clear, specific search query.
    Returns: Top 5 relevant web results with summaries."""
    query = query.strip().lower()

    if query in _cache:
        return _cache[query]

    result = _search_tool.invoke(query)
    _cache[query] = result
    return result