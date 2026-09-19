import os
from dataclasses import dataclass, field
from typing import List


def _get_bool(env_name: str, default: bool) -> bool:
    val = os.getenv(env_name, "").strip().lower()
    if not val:
        return default
    return val in ("true", "1", "yes", "on")


def _get_int(env_name: str, default: int) -> int:
    val = os.getenv(env_name, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_int_list(env_name: str, default: List[int]) -> List[int]:
    val = os.getenv(env_name, "").strip()
    if not val:
        return default
    try:
        return [int(x.strip()) for x in val.split(",") if x.strip()]
    except ValueError:
        return default


@dataclass
class Settings:
    alpha_api_url: str = field(
        default_factory=lambda: os.getenv(
            "ALPHA_API_URL", "https://alpha123.uk/api/data?fresh=1"
        ).strip()
    )

    bark_base_url: str = field(
        default_factory=lambda: os.getenv("BARK_BASE_URL", "").strip()
    )
    bark_server: str = field(
        default_factory=lambda: os.getenv("BARK_SERVER", "").strip()
    )
    bark_device_key: str = field(
        default_factory=lambda: os.getenv("BARK_DEVICE_KEY", "").strip()
    )
    bark_group: str = field(
        default_factory=lambda: os.getenv("BARK_GROUP", "Alpha123").strip()
    )
    bark_sound: str = field(
        default_factory=lambda: os.getenv("BARK_SOUND", "alarm").strip()
    )
    bark_level: str = field(
        default_factory=lambda: os.getenv("BARK_LEVEL", "timeSensitive").strip()
    )

    poll_interval_seconds: int = field(
        default_factory=lambda: _get_int("POLL_INTERVAL_SECONDS", 20)
    )
    max_consecutive_failures: int = field(
        default_factory=lambda: _get_int("MAX_CONSECUTIVE_FAILURES", 10)
    )
    timezone: str = field(
        default_factory=lambda: os.getenv("TIMEZONE", "Asia/Shanghai").strip()
    )

    notify_existing_on_first_run: bool = field(
        default_factory=lambda: _get_bool("NOTIFY_EXISTING_ON_FIRST_RUN", False)
    )

    reminder_minutes: List[int] = field(
        default_factory=lambda: _get_int_list("REMINDER_MINUTES", [20, 5])
    )
    database_path: str = field(
        default_factory=lambda: os.getenv("DATABASE_PATH", "/data/alpha_monitor.db").strip()
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").strip()
    )

    health_server_enabled: bool = field(
        default_factory=lambda: _get_bool("HEALTH_SERVER_ENABLED", True)
    )
    health_server_port: int = field(
        default_factory=lambda: _get_int("HEALTH_SERVER_PORT", 18181)
    )


settings = Settings()
