from datetime import datetime, timedelta
import glob
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.alpha_client import AlphaClient, AlphaClientError
from app.bark import BarkNotifier
from app.config import settings
from app.database import Database
from app.health import global_health_state, start_health_server
from app.models import AirdropEvent
from app.parser import parse_airdrop_data

logger = logging.getLogger("alpha_monitor.monitor")
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class MonitorService:
    def __init__(
        self,
        db: Optional[Database] = None,
        alpha_client: Optional[AlphaClient] = None,
        notifier: Optional[BarkNotifier] = None,
    ):
        self.db = db or Database()
        self.alpha_client = alpha_client or AlphaClient()
        self.notifier = notifier or BarkNotifier()

        self.consecutive_failures = 0
        self.outage_alert_sent = False
        self.is_first_run = False

    def setup(self) -> None:
        """Initialize database, health server, and determine initial state."""
        self.db.init_db()
        global_health_state.event_count_getter = self.db.get_event_count

        if settings.health_server_enabled:
            start_health_server(settings.health_server_port)

        stored_events = self.db.get_all_events()
        if len(stored_events) == 0:
            self.is_first_run = True
            logger.info("First run detected: Database is empty.")
        else:
            self.is_first_run = False
            logger.info(f"Monitor setup complete: Loaded {len(stored_events)} existing events.")

    def save_debug_sample(self, raw_payload: Any) -> None:
        """Save sample response to /data/debug/ capped at max 10 files."""
        try:
            debug_dir = os.path.join(os.path.dirname(os.path.abspath(settings.database_path)), "debug")
            os.makedirs(debug_dir, exist_ok=True)

            timestamp = datetime.now(SHANGHAI_TZ).strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(debug_dir, f"alpha_response_{timestamp}.json")

            dumped = json.dumps(raw_payload, ensure_ascii=False, indent=2)
            # Cap file size at 100KB
            if len(dumped) > 100 * 1024:
                dumped = dumped[: 100 * 1024] + "\n... [Truncated due to size limit]"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(dumped)

            logger.info(f"Saved debug response sample to {filename}")

            # Maintain maximum 10 latest files
            files = sorted(glob.glob(os.path.join(debug_dir, "alpha_response_*.json")))
            if len(files) > 10:
                for old_file in files[:-10]:
                    try:
                        os.remove(old_file)
                    except OSError:
                        pass
        except Exception as e:
            logger.error(f"Failed to save debug response sample: {e}")

    def format_time_str(self, dt: Optional[datetime]) -> str:
        if not dt:
            return "待定"
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def run_once(self) -> None:
        """Execute a single polling iteration."""
        now = datetime.now(SHANGHAI_TZ)
        logger.info(f"--- Starting polling cycle at {now.strftime('%Y-%m-%d %H:%M:%S')} ---")

        # Step 1: Request Data
        raw_payload = None
        try:
            raw_payload = self.alpha_client.fetch_raw_data()
        except AlphaClientError as err:
            self.consecutive_failures += 1
            global_health_state.increment_failure()
            logger.error(
                f"Alpha123 API fetch error (Consecutive failures: {self.consecutive_failures}): {err}"
            )

            if (
                self.consecutive_failures >= settings.max_consecutive_failures
                and not self.outage_alert_sent
            ):
                self.notifier.send(
                    title="⚠️ Alpha123 数据获取失败",
                    body=f"接口已经连续失败 {settings.max_consecutive_failures} 次，请检查网络或接口状态。",
                )
                self.outage_alert_sent = True
            return


        # Handle Outage Recovery
        if self.outage_alert_sent:
            self.notifier.send(
                title="✅ Alpha123 数据恢复",
                body="数据接口已经恢复正常。",
            )
            self.outage_alert_sent = False

        self.consecutive_failures = 0
        global_health_state.update_success(now.isoformat())

        # Step 2: Parse events
        events, summary = parse_airdrop_data(raw_payload)
        logger.info(
            f"Parsed {len(events)} events from API response (Root: {summary['root_type']})"
        )

        old_events = self.db.get_all_events()

        # Step 3: Handle empty parsing / Schema change protection
        if len(events) == 0:
            is_schema_anomaly = (
                len(old_events) > 0 and not summary.get("valid_list_found", False)
            ) or (
                summary.get("total_failed", 0) > 0
            )

            if is_schema_anomaly:
                logger.warning(
                    "API request succeeded but zero events parsed while database has existing events or items failed parsing! Possible schema change."
                )
                self.save_debug_sample(raw_payload)
                self.notifier.send(
                    title="⚠️ Alpha123 数据结构可能变化",
                    body="接口请求成功，但未解析出空投数据，请检查日志。",
                )
            else:
                logger.info("No airdrop events currently returned by API.")


        # Step 4: Process First Run vs Normal Run
        if self.is_first_run:
            logger.info("Executing first-run strategy...")
            for evt in events:
                self.db.upsert_event(evt)

            if settings.notify_existing_on_first_run:
                logger.info("NOTIFY_EXISTING_ON_FIRST_RUN is enabled. Sending notifications for existing events...")
                for evt in events:
                    self._send_new_airdrop_notification(evt)
            else:
                self.notifier.send(
                    title="✅ Alpha123 监控已启动",
                    body=f"已加载 {len(events)} 个空投事件，轮询间隔 {settings.poll_interval_seconds} 秒。",
                )

            self.is_first_run = False
        else:
            # Normal iteration: Check additions & changes
            for evt in events:
                if evt.event_id not in old_events:
                    # New Event
                    logger.info(f"New event detected: {evt.project_name} (ID: {evt.event_id})")
                    self._send_new_airdrop_notification(evt)
                else:
                    # Existing Event: Check for changes
                    old_evt = old_events[evt.event_id]
                    diff = evt.get_diff(old_evt)
                    if diff:
                        logger.info(f"Event updated: {evt.project_name} - Changes: {diff}")
                        self._send_changed_notification(evt, diff)

                self.db.upsert_event(evt)

        # Step 5: Check countdown and start reminders
        current_all_events = self.db.get_all_events()
        for evt in current_all_events.values():
            self._check_reminders(evt, now)

        logger.info(f"Poll cycle complete. Total tracked events: {len(current_all_events)}")

    def _send_new_airdrop_notification(self, event: AirdropEvent) -> None:
        """Send notification for a newly detected airdrop project."""
        notif_key = f"{event.event_id}_new"
        if self.db.is_notification_sent(event.event_id, "new"):
            return

        title = f"🪂 新空投：{event.project_name}"
        time_str = self.format_time_str(event.start_time)
        body = (
            f"积分：{event.points or '无'}\n"
            f"奖励：{event.reward or '无'}\n"
            f"时间：{time_str}\n"
            f"状态：{event.status or '未知'}"
        )

        success = self.notifier.send(
            title=title,
            body=body,
            url=event.safe_detail_url(),
        )
        self.db.record_notification(
            event_id=event.event_id,
            notification_type="new",
            notification_key=notif_key,
            success=success,
        )

    def _send_changed_notification(
        self, event: AirdropEvent, diff: Dict[str, tuple]
    ) -> None:
        """Send notification for updated fields of an airdrop project."""
        notif_key = f"{event.event_id}_changed_{event.raw_hash}"
        if self.db.is_notification_sent(
            event.event_id, "changed", notification_key=notif_key
        ):
            return

        title = f"🔄 空投信息更新：{event.project_name}"
        field_labels = {
            "points": "积分",
            "reward": "奖励",
            "start_time": "时间",
            "status": "状态",
        }

        diff_lines = []
        for field, (old_val, new_val) in diff.items():
            label = field_labels.get(field, field)
            diff_lines.append(f"{label}：{old_val} → {new_val}")

        body = "\n".join(diff_lines)
        success = self.notifier.send(
            title=title,
            body=body,
            url=event.safe_detail_url(),
        )
        self.db.record_notification(
            event_id=event.event_id,
            notification_type="changed",
            notification_key=notif_key,
            success=success,
        )

    def _check_reminders(self, event: AirdropEvent, now: datetime) -> None:
        """Check 20-min, 5-min, and started reminders for an event."""
        if not event.start_time:
            return

        delta_seconds = (event.start_time - now).total_seconds()
        delta_minutes = delta_seconds / 60.0
        time_str = self.format_time_str(event.start_time)
        detail_url = event.safe_detail_url()

        # 1. 20-min Reminder (20 minutes before start, e.g. 0 < delta_minutes <= 20)
        if 0 <= delta_minutes <= 20:
            if not self.db.is_notification_sent(event.event_id, "twenty_minutes"):
                title = f"⏰ 20分钟后空投：{event.project_name}"
                body = (
                    f"开始时间：{time_str}\n"
                    f"积分要求：{event.points or '无'}\n"
                    f"奖励：{event.reward or '无'}\n"
                    f"请提前打开 Binance Alpha 页面准备。"
                )
                success = self.notifier.send(
                    title=title,
                    body=body,
                    url=detail_url,
                )
                self.db.record_notification(
                    event_id=event.event_id,
                    notification_type="twenty_minutes",
                    notification_key=f"{event.event_id}_twenty_minutes",
                    success=success,
                )

        # 2. 5-min Reminder (5 minutes before start, e.g. 0 < delta_minutes <= 5)
        if 0 <= delta_minutes <= 5:
            if not self.db.is_notification_sent(event.event_id, "five_minutes"):
                title = f"🚨 5分钟后空投：{event.project_name}"
                body = (
                    f"开始时间：{time_str}\n"
                    f"积分要求：{event.points or '无'}\n"
                    f"奖励：{event.reward or '无'}\n"
                    f"请提前打开 Binance Alpha 页面准备。"
                )
                success = self.notifier.send(
                    title=title,
                    body=body,
                    url=detail_url,
                    level="timeSensitive",
                    sound="alarm",
                )
                self.db.record_notification(
                    event_id=event.event_id,
                    notification_type="five_minutes",
                    notification_key=f"{event.event_id}_five_minutes",
                    success=success,
                )

        # 3. Started Reminder (start_time reached, within recent window of 15 min)
        if delta_seconds <= 0 and abs(delta_seconds) <= 15 * 60:
            if not self.db.is_notification_sent(event.event_id, "started"):
                title = f"🔥 空投已开始：{event.project_name}"
                body = (
                    f"开始时间：{time_str}\n"
                    f"积分要求：{event.points or '无'}\n"
                    f"奖励：{event.reward or '无'}"
                )
                success = self.notifier.send(
                    title=title,
                    body=body,
                    url=detail_url,
                )
                self.db.record_notification(
                    event_id=event.event_id,
                    notification_type="started",
                    notification_key=f"{event.event_id}_started",
                    success=success,
                )

    def start_loop(self) -> None:
        """Start persistent monitoring polling loop."""
        self.setup()
        logger.info(
            f"Starting Alpha123 Monitor Loop (Polling interval: {settings.poll_interval_seconds}s)..."
        )
        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Unexpected error in monitoring loop: {e}", exc_info=True)

            time.sleep(settings.poll_interval_seconds)
