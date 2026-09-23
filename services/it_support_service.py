"""IT-support capability interface."""

def get_chat_tools() -> list:
    from tools.search_tool import search_with_cache
    return [search_with_cache]
