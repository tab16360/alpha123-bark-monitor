import logging
import re
import time
from typing import Any, Dict, Optional
import httpx

from app.config import settings

logger = logging.getLogger("alpha_monitor.bark")


class BarkNotifier:
    """Handles sending push notifications via Bark with retries and key masking."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        server: Optional[str] = None,
        device_key: Optional[str] = None,
        group: Optional[str] = None,
        sound: Optional[str] = None,
        level: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.bark_base_url).strip()
        self.server = (server or settings.bark_server).strip()
        self.device_key = (device_key or settings.bark_device_key).strip()
        self.group = group or settings.bark_group
        self.sound = sound or settings.bark_sound
        self.level = level or settings.bark_level

    def _resolve_target(self) -> tuple[str, Optional[str]]:
        """Resolve push target URL and optional device_key based on priority.

        Returns (url, device_key)
        """
        if self.base_url:
            url = self.base_url.rstrip("/")
            if url.endswith("/push"):
                # e.g., https://api.day.app/push
                return url, self.device_key if self.device_key else None
            return url, None

        if self.server and self.device_key:
            server = self.server.rstrip("/")
            url = f"{server}/push"
            return url, self.device_key

        return "", None

    def _mask_url(self, url: str) -> str:
        """Mask device keys in URL string for safe logging."""
        return re.sub(r"(https?://[^/]+/)([a-zA-Z0-9_\-]{10,})", r"\1*****", url)

    def send(
        self,
        title: str,
        body: str,
        url: Optional[str] = None,
        group: Optional[str] = None,
        sound: Optional[str] = None,
        level: Optional[str] = None,
    ) -> bool:
        """Send notification via Bark with retries.

        Retries: 3 attempts total with delays 2s, 5s, 10s.
        """
        target_url, device_key = self._resolve_target()
        if not target_url:
            logger.warning(
                "Bark notification skipped: BARK_BASE_URL or (BARK_SERVER + BARK_DEVICE_KEY) is not configured."
            )
            return False

        payload: Dict[str, Any] = {
            "title": title,
            "body": body,
            "group": group or self.group,
            "sound": sound or self.sound,
            "level": level or self.level,
        }

        if device_key:
            payload["device_key"] = device_key

        target_link = url or "https://alpha123.uk/"
        payload["url"] = target_link

        masked_target = self._mask_url(target_url)
        delays = [2, 5, 10]
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(target_url, json=payload)
                    if resp.status_code == 200:
                        logger.info(
                            f"Bark push succeeded (Attempt {attempt}/{max_attempts}) -> '{title}'"
                        )
                        return True
                    else:
                        truncated_body = resp.text[:200].replace("\n", " ")
                        logger.warning(
                            f"Bark push returned non-200 status {resp.status_code} "
                            f"(Attempt {attempt}/{max_attempts}) Target: {masked_target} Body: {truncated_body!r}"
                        )
            except Exception as e:
                logger.warning(
                    f"Bark push request exception (Attempt {attempt}/{max_attempts}) "
                    f"Target: {masked_target} Error: {e}"
                )

            if attempt < max_attempts:
                sleep_time = delays[attempt - 1]
                logger.info(f"Retrying Bark push in {sleep_time} seconds...")
                time.sleep(sleep_time)

        logger.error(f"Bark push failed after {max_attempts} attempts for title: '{title}'")
        return False
