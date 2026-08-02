from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Dict, List, Optional
from urllib.parse import urlparse


@dataclass
class AirdropEvent:
    event_id: str
    project_name: str
    points: Optional[str] = None
    reward: Optional[str] = None
    start_time: Optional[datetime] = None
    status: Optional[str] = None
    detail_url: Optional[str] = None
    raw_hash: str = ""

    def __post_init__(self) -> None:
        if not self.raw_hash:
            self.raw_hash = self.compute_raw_hash()

    def compute_raw_hash(self) -> str:
        """Generate MD5 hash representing key event data attributes."""
        st_str = self.start_time.isoformat() if self.start_time else ""
        content = f"{self.project_name}|{self.points or ''}|{self.reward or ''}|{st_str}|{self.status or ''}|{self.detail_url or ''}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_stable_id(project_name: str, date_str: str, raw_fields_str: str) -> str:
        """Generate stable event ID when API does not provide an explicit ID."""
        content = f"{project_name.strip()}_{date_str.strip()}_{raw_fields_str.strip()}"
        return f"evt_{hashlib.md5(content.encode('utf-8')).hexdigest()[:16]}"

    def safe_detail_url(self, allowed_hosts: Optional[List[str]] = None) -> str:
        """Return detail_url if it is safe and HTTPS, otherwise default to https://alpha123.uk/."""
        default_url = "https://alpha123.uk/"
        if not self.detail_url:
            return default_url

        try:
            parsed = urlparse(self.detail_url.strip())
            if parsed.scheme != "https":
                return default_url

            hostname = (parsed.hostname or "").lower()
            if not hostname:
                return default_url

            if allowed_hosts is None:
                allowed_hosts = ["alpha123.uk", ".alpha123.uk"]

            is_allowed = False
            for allowed in allowed_hosts:
                if allowed.startswith("."):
                    if hostname.endswith(allowed) or hostname == allowed[1:]:
                        is_allowed = True
                        break
                elif hostname == allowed:
                    is_allowed = True
                    break

            if is_allowed:
                return self.detail_url.strip()
        except Exception:
            pass

        return default_url

    def get_diff(self, old: "AirdropEvent") -> Dict[str, tuple]:
        """Compare attributes with old event and return dict of changed fields: field_name -> (old_val, new_val)."""
        diff = {}

        if (old.points or "") != (self.points or ""):
            diff["points"] = (old.points or "无", self.points or "无")

        if (old.reward or "") != (self.reward or ""):
            diff["reward"] = (old.reward or "无", self.reward or "无")

        old_st_str = old.start_time.strftime("%Y-%m-%d %H:%M:%S") if old.start_time else "未知"
        new_st_str = self.start_time.strftime("%Y-%m-%d %H:%M:%S") if self.start_time else "未知"
        if old_st_str != new_st_str:
            diff["start_time"] = (old_st_str, new_st_str)

        if (old.status or "") != (self.status or ""):
            diff["status"] = (old.status or "未知", self.status or "未知")

        return diff
