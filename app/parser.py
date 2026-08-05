import json
import logging

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from zoneinfo import ZoneInfo

from app.models import AirdropEvent

logger = logging.getLogger("alpha_monitor.parser")
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def parse_datetime(val: Any) -> Optional[datetime]:
    """Parse various timestamp representations into a timezone-aware datetime in Asia/Shanghai."""
    if val is None or val == "":
        return None

    if isinstance(val, (int, float)):
        return _timestamp_to_datetime(val)

    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return None

        # Check numeric string timestamp
        if val_str.isdigit():
            try:
                num = float(val_str)
                return _timestamp_to_datetime(num)
            except ValueError:
                pass

        # Try ISO 8601 parsing
        try:
            dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=SHANGHAI_TZ)
            else:
                dt = dt.astimezone(SHANGHAI_TZ)
            return dt
        except ValueError:
            pass

        # Standard YYYY-MM-DD HH:mm:ss or YYYY-MM-DD HH:mm
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
        ):
            try:
                dt = datetime.strptime(val_str, fmt)
                return dt.replace(tzinfo=SHANGHAI_TZ)
            except ValueError:
                pass

        # Month-Day HH:mm formats (e.g. "08-02 20:00", "08/02 20:00")
        for fmt in ("%m-%d %H:%M:%S", "%m-%d %H:%M", "%m/%d %H:%M:%S", "%m/%d %H:%M"):
            try:
                current_year = datetime.now(SHANGHAI_TZ).year
                dt = datetime.strptime(f"{current_year}-{val_str}", f"%Y-{fmt}")
                return dt.replace(tzinfo=SHANGHAI_TZ)
            except ValueError:
                pass

    logger.warning(f"Failed to parse datetime value: {val!r}")
    return None


def _timestamp_to_datetime(val: Union[int, float]) -> datetime:
    # If millis (usually > 1e11)
    if val > 1e11:
        val = val / 1000.0
    dt_utc = datetime.fromtimestamp(val, tz=timezone.utc)
    return dt_utc.astimezone(SHANGHAI_TZ)


def _extract_field(item: Dict[str, Any], candidates: List[str]) -> Optional[Any]:
    for key in candidates:
        if key in item and item[key] is not None:
            return item[key]
    return None


def parse_airdrop_item(raw_item: Dict[str, Any]) -> Optional[AirdropEvent]:
    """Parse a single raw dict item into AirdropEvent defensively."""
    if not isinstance(raw_item, dict):
        logger.warning(f"Invalid item type (expected dict): {type(raw_item)}")
        return None

    # Project Name candidates
    name = _extract_field(
        raw_item, ["project_name", "projectName", "name", "project", "symbol", "title"]
    )
    if not name:
        logger.warning(f"Skipping item due to missing project name: {raw_item}")
        return None
    project_name = str(name).strip()

    # ID candidates
    raw_id = _extract_field(
        raw_item, ["event_id", "id", "eventId", "project_id", "projectId"]
    )

    # Points candidates
    points = _extract_field(
        raw_item, ["points", "min_points", "point", "threshold", "points_required"]
    )
    points_str = str(points).strip() if points is not None else None

    # Reward candidates
    reward = _extract_field(
        raw_item, ["reward", "amount", "tokens", "pool", "prize", "airdrop_amount"]
    )
    reward_str = str(reward).strip() if reward is not None else None

    # Start Time candidates
    raw_time = _extract_field(
        raw_item,
        [
            "start_time",
            "startTime",
            "start_at",
            "airdrop_time",
            "time",
            "date",
            "claim_time",
        ],
    )
    start_time = parse_datetime(raw_time)

    # Status candidates
    status = _extract_field(raw_item, ["status", "state", "phase"])
    status_str = str(status).strip() if status is not None else None

    # Detail URL candidates
    detail_url = _extract_field(
        raw_item, ["detail_url", "detailUrl", "url", "link", "target_url"]
    )
    detail_url_str = str(detail_url).strip() if detail_url is not None else None

    # Determine event_id
    if raw_id:
        event_id = str(raw_id).strip()
    else:
        time_str = start_time.strftime("%Y%m%d%H%M%S") if start_time else str(raw_time or "")
        raw_fields = f"{points_str}_{reward_str}_{status_str}"
        event_id = AirdropEvent.generate_stable_id(project_name, time_str, raw_fields)

    return AirdropEvent(
        event_id=event_id,
        project_name=project_name,
        points=points_str,
        reward=reward_str,
        start_time=start_time,
        status=status_str,
        detail_url=detail_url_str,
    )


def parse_airdrop_data(payload: Any) -> Tuple[List[AirdropEvent], Dict[str, Any]]:
    """Defensively extract airdrop list from JSON payload.

    Returns:
        (events, summary_info)
    """
    events: List[AirdropEvent] = []
    summary: Dict[str, Any] = {
        "root_type": type(payload).__name__,
        "top_keys": [],
        "total_parsed": 0,
        "total_failed": 0,
        "valid_list_found": False,
    }

    raw_items: List[Any] = []

    if isinstance(payload, dict):
        summary["top_keys"] = list(payload.keys())
        # Search common list keys
        for key in ["airdrops", "data", "items", "projects", "list", "events"]:
            if key in payload and isinstance(payload[key], list):
                raw_items = payload[key]
                summary["valid_list_found"] = True
                break
        else:
            # If dictionary itself has list values or nested lists
            for k, v in payload.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    raw_items = v
                    summary["valid_list_found"] = True
                    break

    elif isinstance(payload, list):
        raw_items = payload
        summary["valid_list_found"] = True

    for item in raw_items:
        if isinstance(item, list):
            # If nested list, iterate items
            for sub in item:
                evt = parse_airdrop_item(sub)
                if evt:
                    events.append(evt)
                else:
                    summary["total_failed"] += 1
        elif isinstance(item, dict):
            evt = parse_airdrop_item(item)
            if evt:
                events.append(evt)
            else:
                summary["total_failed"] += 1

    summary["total_parsed"] = len(events)
    return events, summary

