"""
Phase P-B: Notification Service — Stub Implementation.

Current implementation logs to console + file (no external providers).
Design: Provider-agnostic interface so SMS/Email can be swapped for
Twilio / SendGrid / Africa's Talking in a future iteration.

Usage:
    from services.notification_service import notification_service
    await notification_service.send_email("user@example.com", "Subject", "Body")
    await notification_service.send_sms("+254700000000", "Message")
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

# ── Dedicated loggers for email / SMS ──────────────────────────────────────
# They write to both stdlib console *and* file handlers so we get
# structured evidence of every notification even in local dev.

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

# Email logger
_email_logger = logging.getLogger("mpango.notifications.email")
_email_logger.setLevel(logging.INFO)
_email_handler = logging.FileHandler(_LOG_DIR / "email.log", encoding="utf-8")
_email_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
)
_email_logger.addHandler(_email_handler)

# SMS logger
_sms_logger = logging.getLogger("mpango.notifications.sms")
_sms_logger.setLevel(logging.INFO)
_sms_handler = logging.FileHandler(_LOG_DIR / "sms.log", encoding="utf-8")
_sms_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
)
_sms_logger.addHandler(_sms_handler)


class NotificationService:
    """
    Stub notification service.
    
    Phase P-B: All "sends" are logged locally.
    Future: Replace with real provider calls (Twilio, SendGrid, etc.)
    """

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        """
        Send an email notification.

        Currently: logs to console + logs/email.log.
        Future: Call SendGrid / SES / Africa's Talking Email API.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Plain-text email body.

        Returns:
            True if logged successfully (always True for stub).
        """
        ts = datetime.now(timezone.utc).isoformat()
        message = f"TO={to} | SUBJECT={subject} | BODY={body}"
        _email_logger.info(message)
        # Also log to structured console for dev visibility
        logging.getLogger("mpango.notifications").info(
            "email_sent_stub",
            extra={"to": to, "subject": subject, "timestamp": ts},
        )
        return True

    async def send_sms(self, phone: str, message: str) -> bool:
        """
        Send an SMS notification.

        Currently: logs to console + logs/sms.log.
        Future: Call Twilio / Africa's Talking SMS API.

        Args:
            phone: Recipient phone number (E.164 format preferred).
            message: SMS body (≤ 160 chars for single segment).

        Returns:
            True if logged successfully (always True for stub).
        """
        ts = datetime.now(timezone.utc).isoformat()
        log_msg = f"TO={phone} | MESSAGE={message}"
        _sms_logger.info(log_msg)
        logging.getLogger("mpango.notifications").info(
            "sms_sent_stub",
            extra={"phone": phone, "message": message, "timestamp": ts},
        )
        return True


# Singleton instance — import this from other modules
notification_service = NotificationService()
