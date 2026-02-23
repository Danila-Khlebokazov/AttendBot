import logging
import signal
import sys
import threading
from datetime import datetime

from app.config import get_settings, User, Settings
from app.driver_factory import make_driver
from app.telegram import TelegramClient
from app.services.attendance import AttendanceService
from app.schedule import Schedule


def format_schedule(schedule: Schedule) -> str:
    lines = [f"Timezone: {schedule.tz.key}"]
    for idx, day_rule in schedule.days.items():
        day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][idx]
        if not day_rule.enabled:
            lines.append(f"• {day_name}: off")
            continue
        windows = [f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for s, e in day_rule.windows]
        lines.append(f"• {day_name}: {', '.join(windows) if windows else 'default'}")
    return "\n".join(lines)


def run_user_worker(
    user: User,
    settings: Settings,
    schedule: Schedule,
    stop_event: threading.Event,
    poll_secs: int = 10,
) -> None:
    tg = TelegramClient(settings.tg_bot_token, user.tg_chat_id)

    def create_driver():
        return make_driver(settings.remote_url)

    svc = AttendanceService(
        telegram=tg,
        schedule=schedule,
        base_url=settings.base_url,
        create_driver=create_driver,
        wait_seconds=30,
        driver=None,
    )
    try:
        svc.run_loop(
            user.wsp_login,
            user.wsp_password,
            poll_secs=poll_secs,
            stop_event=stop_event,
        )
    finally:
        svc.shutdown()


def main() -> int:
    settings = get_settings()
    schedule = Schedule.from_toml(settings.schedule_path)
    tz = schedule.tz

    def now_s():
        return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")

    accounts_str = ", ".join(u.wsp_login for u in settings.users)

    def safe_notify(user: User, text: str) -> None:
        try:
            tg = TelegramClient(settings.tg_bot_token, user.tg_chat_id)
            tg.send_message(text)
        except Exception as e:
            logging.warning("Failed to send Telegram notification for %s: %s", user.wsp_login, e)

    def notify_once_per_chat(text: str) -> None:
        """Send one message per distinct tg_chat_id (combined only when same chat)."""
        seen_chat_ids = set()
        for user in settings.users:
            if user.tg_chat_id in seen_chat_ids:
                continue
            seen_chat_ids.add(user.tg_chat_id)
            safe_notify(user, text)

    # One startup message per chat (same text to each distinct chat)
    schedule_text = format_schedule(schedule)
    notify_once_per_chat(
        "🚀 Bot starting\n"
        f"Accounts: {accounts_str}\n"
        f"TZ: {tz.key}\n"
        f"Time: {now_s()}\n\n"
        f"📅 Schedule:\n{schedule_text}",
    )

    stop_events = [threading.Event() for _ in settings.users]
    threads = []
    for user, ev in zip(settings.users, stop_events):
        t = threading.Thread(
            target=run_user_worker,
            args=(user, settings, schedule, ev),
            kwargs={"poll_secs": 10},
            name=f"worker-{user.wsp_login}",
            daemon=False,
        )
        threads.append((user, t, ev))
        t.start()

    def _graceful_shutdown(signum=None, _frame=None):
        try:
            sig_name = signal.Signals(signum).name if signum else "UNKNOWN"
        except Exception:
            sig_name = str(signum)
        logging.info("Shutting down (%s); stopping %s worker(s)", sig_name, len(threads))
        for ev in stop_events:
            ev.set()
        for user, t, _ in threads:
            t.join(timeout=15)
            if t.is_alive():
                logging.warning("Worker %s did not stop in time", user.wsp_login)
        notify_once_per_chat(f"🛑 Bot stopping (signal: {sig_name})\nAccounts: {accounts_str}\nTime: {now_s()}")
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    try:
        for user, t, _ in threads:
            t.join()
    except Exception as e:
        logging.exception("Unexpected error: %s", e)
        notify_once_per_chat(
            "💥 Bot crashed\n"
            f"Error: {type(e).__name__}: {e}\n"
            f"Accounts: {accounts_str}\n"
            f"Time: {now_s()}",
        )
        raise
    finally:
        for ev in stop_events:
            ev.set()
        for _, t, _ in threads:
            t.join(timeout=5)

    return 0


if __name__ == "__main__":
    import os
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    raise SystemExit(main())
