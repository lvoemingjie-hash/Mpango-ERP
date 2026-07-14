"""Bootstrap the first platform operator without exposing setup tokens."""
from __future__ import annotations

import argparse
import asyncio
import sys

from database.session import AsyncSessionLocal
from services.platform_operator_service import (
    EmailDeliveryNotConfiguredError,
    PlatformOperatorInvalidStateError,
    PlatformOperatorService,
)


async def _run(email: str) -> int:
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        try:
            await service.bootstrap_first_operator(email=email)
            await session.commit()
        except (EmailDeliveryNotConfiguredError, PlatformOperatorInvalidStateError):
            await session.rollback()
            return 1
    print("Platform operator bootstrap processed. Check the configured email channel.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the first platform operator")
    parser.add_argument("--email", required=True, help="Platform operator email")
    args = parser.parse_args()
    return asyncio.run(_run(args.email))


if __name__ == "__main__":
    sys.exit(main())
