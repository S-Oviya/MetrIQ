"""
MetrIQ API Module
=================
Exposes aggregated REST API routers, OpenAPI schemas, and high-level facades
for Person 1 (Team Lead), Person 2 (Regulatory), Person 3 (Instruments/Jobs),
Person 4 (Test Execution), Person 5 (Evidence), and Person 6 (Reports).
"""

from .router import api_router, __all__ as router_all
from .p3_api import Person3API
from .schemas import success_envelope, error_envelope

__all__ = router_all
