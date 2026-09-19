from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from app.bark import BarkNotifier
from app.database import Database
from app.models import AirdropEvent
from app.monitor import MonitorService


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_monitor.db")
    db = Database(db_file)
    db.init_db()
    return db


def test_first_run_no_bulk_notifications(temp_db):
    mock_notifier = MagicMock(spec=BarkNotifier)
    mock_notifier.send.return_value = True

    mock_client = MagicMock()
    mock_client.fetch_raw_data.return_value = {
        "airdrops": [
            {"id": "e1", "project_name": "Project 1", "points": "100"},
            {"id": "e2", "project_name": "Project 2", "points": "200"},
        ]
    }

    service = MonitorService(db=temp_db, alpha_client=mock_client, notifier=mock_notifier)
    service.setup()
    service.run_once()

    # Database should store 2 events
    assert temp_db.get_event_count() == 2

    # Should send 1 startup notification, NOT individual new airdrop notifications
    assert mock_notifier.send.call_count == 1
    call_args = mock_notifier.send.call_args_list[0][1]
    assert "✅ Alpha123 监控已启动" in call_args["title"]


def test_field_change_notification(temp_db):
    mock_notifier = MagicMock(spec=BarkNotifier)
    mock_notifier.send.return_value = True

    mock_client = MagicMock()
    # Step 1: Initial event
    mock_client.fetch_raw_data.return_value = {
        "airdrops": [
            {"id": "e1", "project_name": "Project 1", "points": "100", "reward": "50 TOKEN"}
        ]
    }

    service = MonitorService(db=temp_db, alpha_client=mock_client, notifier=mock_notifier)
    service.setup()
    service.run_once()  # First run

    mock_notifier.reset_mock()

    # Step 2: Points changed from 100 to 200
    mock_client.fetch_raw_data.return_value = {
        "airdrops": [
            {"id": "e1", "project_name": "Project 1", "points": "200", "reward": "50 TOKEN"}
        ]
    }
    service.run_once()

    # Changed notification should be sent
    assert mock_notifier.send.call_count == 1
    call_kwargs = mock_notifier.send.call_args[1]
    assert "🔄 空投信息更新：Project 1" in call_kwargs["title"]
    assert "积分：100 → 200" in call_kwargs["body"]

    # Step 3: Running again with SAME data should NOT trigger another notification
    mock_notifier.reset_mock()
    service.run_once()
    assert mock_notifier.send.call_count == 0


def test_restart_persistence(temp_db):
    mock_notifier = MagicMock(spec=BarkNotifier)
    mock_notifier.send.return_value = True

    mock_client = MagicMock()
    mock_client.fetch_raw_data.return_value = {
        "airdrops": [{"id": "e1", "project_name": "Project 1"}]
    }

    # Instance 1
    service1 = MonitorService(db=temp_db, alpha_client=mock_client, notifier=mock_notifier)
    service1.setup()
    service1.run_once()

    mock_notifier.reset_mock()

    # Instance 2 (simulating app restart using same DB)
    service2 = MonitorService(db=temp_db, alpha_client=mock_client, notifier=mock_notifier)
    service2.setup()  # Not first run anymore
    service2.run_once()

    # Should not re-send startup or new notification
    assert mock_notifier.send.call_count == 0


def test_schema_change_protection_does_not_clear_db(temp_db):
    mock_notifier = MagicMock(spec=BarkNotifier)
    mock_notifier.send.return_value = True

    mock_client = MagicMock()
    mock_client.fetch_raw_data.return_value = {
        "airdrops": [{"id": "e1", "project_name": "Project 1"}]
    }

    service = MonitorService(db=temp_db, alpha_client=mock_client, notifier=mock_notifier)
    service.setup()
    service.run_once()
    assert temp_db.get_event_count() == 1

    mock_notifier.reset_mock()

    # API returns 200 OK but unrecognized keys (e.g. schema changed)
    mock_client.fetch_raw_data.return_value = {"unrecognized_key": 123}
    service.run_once()

    # Database MUST NOT be cleared
    assert temp_db.get_event_count() == 1
    # Schema change alert should be sent
    assert mock_notifier.send.call_count == 1
    assert "⚠️ Alpha123 数据结构可能变化" in mock_notifier.send.call_args[1]["title"]


def test_valid_empty_airdrops_does_not_trigger_schema_alert(temp_db):
    mock_notifier = MagicMock(spec=BarkNotifier)
    mock_notifier.send.return_value = True

    mock_client = MagicMock()
    mock_client.fetch_raw_data.return_value = {
        "airdrops": [{"id": "e1", "project_name": "Project 1"}]
    }

    service = MonitorService(db=temp_db, alpha_client=mock_client, notifier=mock_notifier)
    service.setup()
    service.run_once()
    assert temp_db.get_event_count() == 1

    mock_notifier.reset_mock()

    # API returns valid payload with empty "airdrops" array
    mock_client.fetch_raw_data.return_value = {
        "airdrops": [],
        "alpha_checkins": [],
        "bnb_price_usd": 599.15
    }
    service.run_once()

    # Database retains existing events
    assert temp_db.get_event_count() == 1
    # NO schema change alert should be sent
    assert mock_notifier.send.call_count == 0


def test_consecutive_failures_alert(temp_db):
    from app.alpha_client import AlphaClientError
    from app.config import settings

    mock_notifier = MagicMock(spec=BarkNotifier)
    mock_notifier.send.return_value = True

    mock_client = MagicMock()
    mock_client.fetch_raw_data.side_effect = AlphaClientError("HTTP 403 Forbidden")

    service = MonitorService(db=temp_db, alpha_client=mock_client, notifier=mock_notifier)
    service.setup()
    service.is_first_run = False

    # Fail MAX_CONSECUTIVE_FAILURES - 1 times (9 times by default)

    for _ in range(settings.max_consecutive_failures - 1):
        service.run_once()
        assert mock_notifier.send.call_count == 0

    # 10th failure triggers the alert
    service.run_once()
    assert mock_notifier.send.call_count == 1
    assert "⚠️ Alpha123 数据获取失败" in mock_notifier.send.call_args[1]["title"]
    assert f"接口已经连续失败 {settings.max_consecutive_failures} 次" in mock_notifier.send.call_args[1]["body"]

    # Subsequent failures do not re-send
    mock_notifier.reset_mock()
    service.run_once()
    assert mock_notifier.send.call_count == 0

    # Recovery
    mock_client.fetch_raw_data.side_effect = None
    mock_client.fetch_raw_data.return_value = {"airdrops": []}
    service.run_once()
    assert mock_notifier.send.call_count == 1
    assert "✅ Alpha123 数据恢复" in mock_notifier.send.call_args[1]["title"]


