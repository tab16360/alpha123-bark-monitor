from datetime import datetime
import logging
import os
import sqlite3
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from app.config import settings
from app.models import AirdropEvent

logger = logging.getLogger("alpha_monitor.database")
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.database_path
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create database directory {db_dir}: {e}")

    def get_connection(self) -> sqlite3.Connection:
        self._ensure_dir()
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError as e:
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            logger.error(
                f"SQLite OperationalError opening database '{self.db_path}'. "
                f"Directory '{db_dir}' permission error? Error detail: {e}"
            )
            raise

    def init_db(self) -> None:
        """Create tables if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    points TEXT,
                    reward TEXT,
                    start_time TEXT,
                    status TEXT,
                    detail_url TEXT,
                    raw_hash TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    notification_type TEXT NOT NULL,
                    notification_key TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    error_message TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notif_event_type
                ON notifications(event_id, notification_type, success)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notif_key
                ON notifications(notification_key, success)
                """
            )
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")

    def get_all_events(self) -> Dict[str, AirdropEvent]:
        """Fetch all stored events into a dict keyed by event_id."""
        events: Dict[str, AirdropEvent] = {}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT event_id, project_name, points, reward, start_time, status, detail_url, raw_hash
                FROM events
                """
            )
            rows = cursor.fetchall()
            for r in rows:
                st = None
                if r["start_time"]:
                    try:
                        st = datetime.fromisoformat(r["start_time"])
                    except ValueError:
                        pass

                event = AirdropEvent(
                    event_id=r["event_id"],
                    project_name=r["project_name"],
                    points=r["points"],
                    reward=r["reward"],
                    start_time=st,
                    status=r["status"],
                    detail_url=r["detail_url"],
                    raw_hash=r["raw_hash"],
                )
                events[event.event_id] = event
        return events

    def upsert_event(self, event: AirdropEvent) -> None:
        """Insert or update event in DB."""
        now_str = datetime.now(SHANGHAI_TZ).isoformat()
        st_str = event.start_time.isoformat() if event.start_time else None

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO events (
                    event_id, project_name, points, reward, start_time, status, detail_url, raw_hash, first_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    project_name=excluded.project_name,
                    points=excluded.points,
                    reward=excluded.reward,
                    start_time=excluded.start_time,
                    status=excluded.status,
                    detail_url=excluded.detail_url,
                    raw_hash=excluded.raw_hash,
                    updated_at=excluded.updated_at
                """,
                (
                    event.event_id,
                    event.project_name,
                    event.points,
                    event.reward,
                    st_str,
                    event.status,
                    event.detail_url,
                    event.raw_hash,
                    now_str,
                    now_str,
                ),
            )
            conn.commit()

    def is_notification_sent(
        self,
        event_id: str,
        notification_type: str,
        notification_key: Optional[str] = None,
    ) -> bool:
        """Check if notification was already successfully sent."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if notification_key:
                cursor.execute(
                    """
                    SELECT 1 FROM notifications
                    WHERE notification_key = ? AND success = 1
                    LIMIT 1
                    """,
                    (notification_key,),
                )
            else:
                cursor.execute(
                    """
                    SELECT 1 FROM notifications
                    WHERE event_id = ? AND notification_type = ? AND success = 1
                    LIMIT 1
                    """,
                    (event_id, notification_type),
                )
            return cursor.fetchone() is not None

    def record_notification(
        self,
        event_id: str,
        notification_type: str,
        notification_key: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Record notification attempt into notifications log."""
        now_str = datetime.now(SHANGHAI_TZ).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO notifications (
                    event_id, notification_type, notification_key, sent_at, success, error_message
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    notification_type,
                    notification_key,
                    now_str,
                    1 if success else 0,
                    error_message,
                ),
            )
            conn.commit()

    def get_event_count(self) -> int:
        """Return count of stored events."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM events")
            row = cursor.fetchone()
            return row[0] if row else 0

    def reset_db(self) -> None:
        """Drop all tables and re-initialize."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS notifications")
            cursor.execute("DROP TABLE IF EXISTS events")
            conn.commit()
        self.init_db()
