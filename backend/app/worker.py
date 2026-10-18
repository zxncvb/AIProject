import asyncio
import logging

from .services.workflow import worker_loop


async def main() -> None:
    # Database bootstrap/migrations are owned by the API service. Running
    # create_all concurrently from every worker causes PostgreSQL DDL races.
    logging.basicConfig(level=logging.INFO)
    await worker_loop()


if __name__ == "__main__":
    asyncio.run(main())
