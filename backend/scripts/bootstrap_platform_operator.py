"""Bootstrap the first platform operator without exposing setup tokens."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from database.session import AsyncSessionLocal
from services.platform_operator_service import (
    EmailDeliveryNotConfiguredError,
    PlatformOperatorInvalidStateError,
    PlatformOperatorRecoveryInvalidError,
    PlatformOperatorService,
)


async def _run(email: str, recovery_credential: str) -> int:
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        try:
            await service.bootstrap_first_operator(
                email=email,
                recovery_credential=recovery_credential,
            )
            await session.commit()
        except (
            EmailDeliveryNotConfiguredError,
            PlatformOperatorInvalidStateError,
            PlatformOperatorRecoveryInvalidError,
        ):
            await session.rollback()
            return 1
    print("Platform operator bootstrap processed. Check the configured email channel.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the first platform operator")
    parser.add_argument("--email", required=True, help="Platform operator email")
    args = parser.parse_args()
    recovery_credential = getpass.getpass("Recovery credential: ")
    confirm_recovery_credential = getpass.getpass("Confirm recovery credential: ")
    if recovery_credential != confirm_recovery_credential:
        return 1
    return asyncio.run(_run(args.email, recovery_credential))


if __name__ == "__main__":
    sys.exit(main())
