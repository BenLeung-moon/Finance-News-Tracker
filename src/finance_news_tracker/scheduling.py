from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from finance_news_tracker.config import Settings

logger = logging.getLogger(__name__)


def should_run_today(run_weekdays_only: bool, timezone: str) -> bool:
    """Return whether the scheduled workflow should run today.

    Uses datetime.weekday() where Monday=0 and Sunday=6. When
    run_weekdays_only is False, always returns True. Holiday calendars are
    intentionally not checked in v1 (see HOLIDAY_GUARD_ENABLED for future use).
    """
    if not run_weekdays_only:
        return True
    now = datetime.now(ZoneInfo(timezone))
    return now.weekday() < 5


@contextmanager
def acquire_run_lock(lock_path: Path) -> Iterator[None]:
    """Prevent overlapping scheduled runs within the same data directory.

    Uses an exclusive create (O_EXCL) so a second process exits immediately
    instead of waiting. Host-level flock in cron is still recommended.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        yield
    except FileExistsError as exc:
        raise RuntimeError(
            f"Another run appears to be in progress (lock: {lock_path})"
        ) from exc
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove run lock at %s", lock_path)


def should_run_scheduled(settings: Settings) -> bool:
    """Application-level guard; complements cron's Mon-Fri schedule."""
    if settings.holiday_guard_enabled:
        # Reserved for future holiday file / calendar integration.
        logger.warning(
            "HOLIDAY_GUARD_ENABLED is true but holiday calendars are not "
            "implemented yet; only weekday guard is applied."
        )
    return should_run_today(settings.run_weekdays_only, settings.run_timezone)
