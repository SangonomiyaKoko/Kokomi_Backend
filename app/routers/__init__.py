
from .bot_urls import router as bot_router
from .platform_urls import router as platform_router
from .demo_urls import router as demo_router
from .statistics_urls import router as statistics_router
from .recent_urls import router as recent_router

__all__ = [
    'bot_router',
    'platform_router',
    'demo_router',
    'statistics_router',
    'recent_router'
]