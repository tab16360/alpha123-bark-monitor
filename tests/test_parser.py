from datetime import datetime
import json
import os
import pytest
from zoneinfo import ZoneInfo

from app.models import AirdropEvent
from app.parser import parse_airdrop_data, parse_airdrop_item, parse_datetime

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def test_parse_datetime_formats():
    # Unix seconds (e.g. 1785673824 = 2026-08-02 12:30:24 UTC = 20:30:24 +08:00)
    dt1 = parse_datetime(1785673824)
    assert dt1 is not None
    assert dt1.tzinfo == SHANGHAI_TZ

    # Unix millis
    dt2 = parse_datetime(1785673824000)
    assert dt2 is not None
    assert dt2.tzinfo == SHANGHAI_TZ
    assert dt1 == dt2

    # ISO 8601
    dt3 = parse_datetime("2026-08-02T20:30:24+08:00")
    assert dt3 is not None
    assert dt3.year == 2026 and dt3.hour == 20 and dt3.minute == 30

    # YYYY-MM-DD HH:mm:ss
    dt4 = parse_datetime("2026-08-02 20:30:24")
    assert dt4 is not None
    assert dt4.year == 2026 and dt4.hour == 20

    # Month-Day string
    dt5 = parse_datetime("08-02 20:30")
    assert dt5 is not None
    assert dt5.month == 8 and dt5.day == 2 and dt5.hour == 20


def test_parse_airdrop_item_missing_fields():
    # Minimal valid item
    raw = {"name": "Minimal Project"}
    event = parse_airdrop_item(raw)
    assert event is not None
    assert event.project_name == "Minimal Project"
    assert event.event_id.startswith("evt_")
    assert event.points is None
    assert event.reward is None
    assert event.start_time is None


def test_parse_airdrop_data_dict_root():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_response.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    events, summary = parse_airdrop_data(data)
    assert len(events) == 3
    assert summary["root_type"] == "dict"
    assert events[0].project_name == "Test Project A"
    assert events[0].points == "180"
    assert events[1].event_id == "evt_1002"


def test_parse_airdrop_data_array_root():
    data = [
        {"id": "a1", "project_name": "Proj 1", "points": "10"},
        {"id": "a2", "project_name": "Proj 2", "points": "20"},
    ]
    events, summary = parse_airdrop_data(data)
    assert len(events) == 2
    assert summary["root_type"] == "list"


def test_safe_detail_url():
    evt_safe = AirdropEvent(
        event_id="1",
        project_name="P1",
        detail_url="https://alpha123.uk/airdrop/123",
    )
    assert evt_safe.safe_detail_url() == "https://alpha123.uk/airdrop/123"

    evt_subdomain = AirdropEvent(
        event_id="2",
        project_name="P2",
        detail_url="https://sub.alpha123.uk/page",
    )
    assert evt_subdomain.safe_detail_url() == "https://sub.alpha123.uk/page"

    evt_unsafe = AirdropEvent(
        event_id="3",
        project_name="P3",
        detail_url="https://malicious-site.com/steal-keys",
    )
    assert evt_unsafe.safe_detail_url() == "https://alpha123.uk/"

    evt_http = AirdropEvent(
        event_id="4",
        project_name="P4",
        detail_url="http://alpha123.uk/insecure",
    )
    assert evt_http.safe_detail_url() == "https://alpha123.uk/"


def test_parse_mystery_box_item():
    raw = {
        "token": "",
        "date": "2026-08-06",
        "time": "19:00",
        "points": "245",
        "type": "grab",
        "phase": 1,
        "language": "zh",
        "status": "announced",
        "box": True,
        "futures_listed": False,
        "amount": "",
        "name": "",
        "created_timestamp": 1786006875,
        "updated_timestamp": 1786007946,
        "system_timestamp": 1786007946,
        "total_quota": "13316",
        "quota_event_id": "mystery_box_6a7462413de700.47565405",
        "quota_type": "box",
        "quota_source": "telegram_binance_velocity_cn",
        "quota_received_at": "2026-08-06 18:30:25",
        "quota_expires_at": "2026-08-06 19:30:00",
    }
    events, summary = parse_airdrop_data({"airdrops": [raw]})
    assert len(events) == 1
    evt = events[0]
    assert evt.event_id == "mystery_box_6a7462413de700.47565405"
    assert evt.project_name == "神秘盲盒"
    assert evt.points == "245"
    assert "13316" in evt.reward
    assert evt.start_time is not None
    assert evt.start_time.year == 2026 and evt.start_time.month == 8 and evt.start_time.day == 6 and evt.start_time.hour == 19
    assert evt.status == "announced"

