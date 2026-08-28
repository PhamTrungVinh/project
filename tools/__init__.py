from .search_tool import search_with_cache
from .calculator_tool import calculator_tool
from .ticket_tools import build_ticket_tools
from .booking_tools import build_booking_tools
from .memory_tools import build_memory_tools

STATIC_WEB_TOOLS = [search_with_cache, calculator_tool]