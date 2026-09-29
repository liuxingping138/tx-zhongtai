import asyncio
import logging

from app.worker.scheduler import main

logging.basicConfig(level=logging.INFO)
asyncio.run(main())
