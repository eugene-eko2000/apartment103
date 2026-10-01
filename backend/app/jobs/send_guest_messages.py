"""Daily job: send the automated guest messages that fell due today.

What is due, and how a message is sent exactly once, is decided in
app.services.guest_messages. This module only schedules it: once a day at
settings.guest_message_send_hour_utc (12:00 UTC by default), so guests in
Europe get their messages around lunchtime rather than in the night.

Runs in-process via APScheduler on the shared scheduler in app.jobs.scheduler.
Running it twice is harmless: every (template, booking) pair is claimed by a
unique delivery row before anything is sent.
"""

import logging

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.services.guest_messages import send_due_messages

logger = logging.getLogger(__name__)

JOB_ID = "send_guest_messages"


async def send_guest_messages() -> int:
    try:
        sent = await send_due_messages()
    except Exception:
        # Tomorrow's run catches up on what this one missed (see
        # settings.guest_message_catch_up_days).
        logger.exception("Failed to send guest messages")
        return 0
    if sent:
        logger.info("Sent %d guest message(s)", sent)
    return sent


def register(scheduler: BaseScheduler) -> None:
    scheduler.add_job(
        send_guest_messages,
        CronTrigger(
            hour=settings.guest_message_send_hour_utc,
            minute=settings.guest_message_send_minute_utc,
            timezone="UTC",
        ),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
