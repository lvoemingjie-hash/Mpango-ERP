"""Break-glass recovery for platform operators.

The recovery credential is read only from hidden stdin. The command never sets
or prints a password or reset token.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from database.session import AsyncSessionLocal
from services.platform_operator_service import (
    EmailDeliveryNotConfiguredError,
    PlatformOperatorRecoveryInvalidError,
    PlatformOperatorService,
)


async def _run(email: str) -> int:
    recovery_credential = getpass.getpass("Recovery credential: ")
    replacement_credential = getpass.getpass("Replacement recovery credential: ")
    confirm_replacement_credential = getpass.getpass("Confirm replacement recovery credential: ")
    if replacement_credential != confirm_replacement_credential:
        return 1
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        try:
            await service.break_glass_recover(
                raw_credential=recovery_credential,
                replacement_credential=replacement_credential,
                operator_email=email,
            )
            await session.commit()
        except (EmailDeliveryNotConfiguredError, PlatformOperatorRecoveryInvalidError):
            await session.rollback()
            return 1
    print("Break-glass recovery processed. Check the configured email channel.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover one platform operator")
    parser.add_argument("--email", required=True, help="Operator email to recover")
    args = parser.parse_args()
    return asyncio.run(_run(args.email))


if __name__ == "__main__":
    sys.exit(main())
