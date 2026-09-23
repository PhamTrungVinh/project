"""Web-tool capability interface."""

def get_support_search_tool():
    from tools.search_tool import search_with_cache
    return search_with_cache
