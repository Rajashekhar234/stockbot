"""
Entry point.

Usage:
  python main.py            # run today (waits for 09:30 IST then trades)
  python main.py --now      # run immediately regardless of time (testing)
  python main.py --schedule # daemon mode: schedules itself every weekday 08:55 IST
"""
from __future__ import annotations

import argparse
import time

import schedule

from src.orchestrator import run_day
from src.utils.logger import get_logger

log = get_logger("main")


def _scheduled():
    log.info("Scheduler tick — kicking off daily run")
    try:
        run_day()
    except Exception as e:
        log.exception("Daily run crashed: %s", e)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--now", action="store_true", help="run immediately, ignore time gating")
    p.add_argument("--schedule", action="store_true", help="run as daemon, kick off 08:55 IST every weekday")
    args = p.parse_args()

    if args.schedule:
        schedule.every().monday.at("08:55").do(_scheduled)
        schedule.every().tuesday.at("08:55").do(_scheduled)
        schedule.every().wednesday.at("08:55").do(_scheduled)
        schedule.every().thursday.at("08:55").do(_scheduled)
        schedule.every().friday.at("08:55").do(_scheduled)
        log.info("Daemon armed. Waiting for next 08:55 IST trigger…")
        while True:
            schedule.run_pending()
            time.sleep(30)

    log.info("Starting one-shot run (now=%s)", args.now)
    run_day()


if __name__ == "__main__":
    main()
