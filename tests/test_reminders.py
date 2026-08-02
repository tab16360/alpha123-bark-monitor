from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest
from zoneinfo import ZoneInfo

from app.bark import BarkNotifier
from app.database import Database
from app.models import AirdropEvent
from app.monitor import MonitorService

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_reminders.db")
    db = Database(db_file)
    db.init_db()
    return db


def test_timing_reminders_sequence(temp_db):
    mock_notifier = MagicMock(spec=BarkNotifier)
    mock_notifier.send.return_value = True

    base_time = datetime(2026, 8, 2, 20, 0, 0, tzinfo=SHANGHAI_TZ)
    # Event starts at 20:30 (in 30 mins from base_time)
    start_time = base_time + timedelta(minutes=30)

    event = AirdropEvent(
        event_id="evt_rem",
        project_name="Countdown Token",
        points="500",
        reward="100 CT",
        start_time=start_time,
        status="upcoming",
    )
    temp_db.upsert_event(event)

    service = MonitorService(db=temp_db, notifier=mock_notifier)

    # 1. At T=20:00 (30 mins before start): No reminder should be triggered
    service._check_reminders(event, now=base_time)
    assert mock_notifier.send.call_count == 0

    # 2. At T=20:12 (18 mins before start): 20-minute reminder should trigger
    t_20m = base_time + timedelta(minutes=12)
    service._check_reminders(event, now=t_20m)
    assert mock_notifier.send.call_count == 1
    call_args_20m = mock_notifier.send.call_args[1]
    assert "⏰ 20分钟后空投：Countdown Token" in call_args_20m["title"]

    # Re-checking at T=20:15 (15 mins before start): 20m should NOT be sent again
    mock_notifier.reset_mock()
    t_15m = base_time + timedelta(minutes=15)
    service._check_reminders(event, now=t_15m)
    assert mock_notifier.send.call_count == 0

    # 3. At T=20:26 (4 mins before start): 5-minute reminder should trigger
    t_4m = base_time + timedelta(minutes=26)
    service._check_reminders(event, now=t_4m)
    assert mock_notifier.send.call_count == 1
    call_args_5m = mock_notifier.send.call_args[1]
    assert "🚨 5分钟后空投：Countdown Token" in call_args_5m["title"]
    assert call_args_5m["level"] == "timeSensitive"
    assert call_args_5m["sound"] == "alarm"

    # Re-checking at T=20:28 (2 mins before start): 5m should NOT be sent again
    mock_notifier.reset_mock()
    t_2m = base_time + timedelta(minutes=28)
    service._check_reminders(event, now=t_2m)
    assert mock_notifier.send.call_count == 0

    # 4. At T=20:30 (start time reached): Started reminder should trigger
    t_start = start_time
    service._check_reminders(event, now=t_start)
    assert mock_notifier.send.call_count == 1
    call_args_started = mock_notifier.send.call_args[1]
    assert "🔥 空投已开始：Countdown Token" in call_args_started["title"]

    # Re-checking at T=20:32 (2 mins after start): Started should NOT be sent again
    mock_notifier.reset_mock()
    t_after = start_time + timedelta(minutes=2)
    service._check_reminders(event, now=t_after)
    assert mock_notifier.send.call_count == 0
