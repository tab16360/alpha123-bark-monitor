import argparse
import json
import sys
from typing import List, Optional

from app.alpha_client import AlphaClient
from app.bark import BarkNotifier
from app.config import settings
from app.database import Database
from app.logging_config import setup_logging
from app.monitor import MonitorService
from app.parser import parse_airdrop_data


def cmd_run() -> None:
    """Run persistent monitoring daemon."""
    logger = setup_logging(settings.log_level)
    logger.info("Initializing Alpha123 Monitor Service...")
    service = MonitorService()
    service.start_loop()


def cmd_test_bark() -> None:
    """Send a test push notification via Bark."""
    logger = setup_logging("INFO")
    logger.info("Sending test Bark push notification...")
    notifier = BarkNotifier()
    success = notifier.send(
        title="🔔 Alpha123 监控测试",
        body="这是一条测试通知，说明 Bark 推送配置正常！",
        url="https://alpha123.uk/",
    )
    if success:
        logger.info("Test notification sent successfully!")
        sys.exit(0)
    else:
        logger.error("Failed to send test notification. Please check your Bark configuration.")
        sys.exit(1)


def cmd_fetch_once() -> None:
    """Fetch API once, display top-level keys and normalized events."""
    logger = setup_logging("INFO")
    logger.info(f"Fetching Alpha123 data from {settings.alpha_api_url}...")
    client = AlphaClient()
    try:
        raw_payload = client.fetch_raw_data()
        events, summary = parse_airdrop_data(raw_payload)

        print("\n" + "=" * 60)
        print("API RESPONSE SUMMARY")
        print("=" * 60)
        print(f"Root JSON Type: {summary['root_type']}")
        print(f"Top-Level Keys: {summary['top_keys']}")
        print(f"Total Parsed Events: {summary['total_parsed']}")
        print(f"Total Failed Items: {summary['total_failed']}")
        print("=" * 60)

        if events:
            print("\nPARSED AIRDROP EVENTS:")
            for idx, evt in enumerate(events, 1):
                st_str = evt.start_time.strftime("%Y-%m-%d %H:%M:%S") if evt.start_time else "None"
                print(
                    f"[{idx}] ID: {evt.event_id} | Name: {evt.project_name} | Points: {evt.points} | "
                    f"Reward: {evt.reward} | Start: {st_str} | Status: {evt.status}"
                )
        else:
            print("\nNo airdrop events found in current response.")

    except Exception as e:
        logger.error(f"fetch-once failed: {e}")
        sys.exit(1)


def cmd_show_events() -> None:
    """Display events currently stored in SQLite database."""
    logger = setup_logging("INFO")
    db = Database()
    db.init_db()
    events = db.get_all_events()

    print("\n" + "=" * 60)
    print(f"DATABASE STORED EVENTS (Total: {len(events)})")
    print("=" * 60)

    if not events:
        print("No events stored in database.")
        return

    for idx, (evt_id, evt) in enumerate(events.items(), 1):
        st_str = evt.start_time.strftime("%Y-%m-%d %H:%M:%S") if evt.start_time else "None"
        print(
            f"[{idx}] ID: {evt_id} | Name: {evt.project_name} | Points: {evt.points} | "
            f"Reward: {evt.reward} | Start: {st_str} | Status: {evt.status} | URL: {evt.detail_url}"
        )


def cmd_reset_database(skip_confirm: bool = False) -> None:
    """Reset SQLite database after user confirmation."""
    logger = setup_logging("INFO")
    db = Database()
    if not skip_confirm:
        print(f"WARNING: This will erase all data in {settings.database_path}!")
        confirm = input("Are you sure you want to reset database? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Reset database operation cancelled.")
            return

    db.reset_db()
    logger.info("Database reset successfully.")


def main(args: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Alpha123 Airdrop Monitor & Bark Push CLI")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    subparsers.add_parser("run", help="Run persistent monitor loop")
    subparsers.add_parser("test-bark", help="Send test Bark push notification")
    subparsers.add_parser("fetch-once", help="Fetch API once and print normalized results")
    subparsers.add_parser("show-events", help="Show events stored in database")

    reset_parser = subparsers.add_parser("reset-database", help="Reset SQLite database")
    reset_parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )

    parsed = parser.parse_args(args)

    if parsed.command == "run" or not parsed.command:
        cmd_run()
    elif parsed.command == "test-bark":
        cmd_test_bark()
    elif parsed.command == "fetch-once":
        cmd_fetch_once()
    elif parsed.command == "show-events":
        cmd_show_events()
    elif parsed.command == "reset-database":
        cmd_reset_database(skip_confirm=parsed.yes)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
