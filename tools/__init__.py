from .search_tool import search_with_cache
from .calculator_tool import calculator_tool
from .ticket_tools import create_ticket, track_ticket, update_ticket
from .booking_tools import book_room, track_booking, update_booking, cancel_booking
from .memory_tools import remember_fact

ALL_TOOLS = [search_with_cache, calculator_tool, remember_fact]

TICKET_TOOLS = [create_ticket, track_ticket, update_ticket]
BOOKING_TOOLS = [book_room, track_booking, update_booking, cancel_booking]
IT_SUPPORT_TOOLS = [search_with_cache]
