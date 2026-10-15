import asyncio

from platform_common.logging_setup import setup_logging

from app.core.config import get_settings
from app.worker.runner import main

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
asyncio.run(main())
