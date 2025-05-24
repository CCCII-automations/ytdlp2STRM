import schedule
from cli import main as main_cli
from clases.config import config as c
from clases.log import Logger, LogLevel
import threading
import re
from tzlocal import get_localzone
import pytz
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import hashlib
import traceback
import time
from datetime import datetime

# Initialize logger
logger = Logger(
    log_file='logs/cron.log',
    min_level=LogLevel.DEBUG,
    enable_colors=True
)

# -- LOAD CONFIG AND CHANNELS FILES
config_path = 'config/crons.json'


def calculate_hash(file_path):
    """Calculate SHA-256 hash of the specified file with logging."""
    logger.debug("CRON", f"Calculating hash for file: {file_path}")
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        hash_value = sha256.hexdigest()
        logger.debug("CRON", f"Hash calculated successfully", {"file": file_path, "hash": hash_value[:8]})
        return hash_value
    except FileNotFoundError:
        logger.warning("CRON", f"File not found for hash calculation: {file_path}")
        return None
    except Exception as e:
        logger.error("CRON", f"Error calculating hash for {file_path}: {str(e)}")
        return None


def load_crons():
    """Load cron configuration with enhanced logging"""
    logger.info("CRON", f"Loading cron configuration from {config_path}")
    try:
        config_data = c.config(config_path).get_config()
        logger.info("CRON", f"Successfully loaded {len(config_data)} cron jobs")
        logger.debug("CRON", "Cron configuration", {"jobs": config_data})
        return config_data
    except Exception as e:
        logger.error("CRON", f"Failed to load cron configuration: {str(e)}",
                     {"traceback": traceback.format_exc()})
        return []


class Cron(threading.Thread):
    def __init__(self, stop_event):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.observer = Observer()
        self.config_hash = None
        self.scheduled_jobs = []
        logger.info("CRON", "Cron thread initialized", {"daemon": self.daemon})

    def run(self):
        """Main cron thread execution"""
        logger.info("CRON", "Starting cron scheduler thread")
        try:
            self.default_tz = get_localzone()
            logger.info("CRON", f"Default timezone detected: {self.default_tz}")
        except Exception as e:
            logger.error("CRON", f"Failed to detect timezone, using UTC: {str(e)}")
            self.default_tz = pytz.UTC

        self.schedule_tasks()
        self.watch_config()

    def schedule_tasks(self):
        """Schedule tasks based on configuration with detailed logging"""
        logger.info("CRON", "Checking for configuration changes")

        new_hash = calculate_hash(config_path)
        if self.config_hash == new_hash:
            logger.debug("CRON", "Configuration unchanged, skipping reschedule")
            return

        logger.info("CRON", "Configuration changed, rescheduling tasks",
                    {"old_hash": self.config_hash[:8] if self.config_hash else None,
                     "new_hash": new_hash[:8] if new_hash else None})

        self.config_hash = new_hash
        self.crons = load_crons()

        # Cancel existing scheduled jobs
        existing_jobs = schedule.get_jobs()
        if existing_jobs:
            logger.info("CRON", f"Cancelling {len(existing_jobs)} existing jobs")
            for job in existing_jobs:
                schedule.cancel_job(job)

        # Track scheduled jobs for logging
        self.scheduled_jobs = []

        # Schedule all new tasks
        for idx, cron in enumerate(self.crons):
            try:
                self._schedule_single_task(idx, cron)
            except Exception as e:
                logger.error("CRON", f"Failed to schedule task {idx}: {str(e)}",
                             {"cron": cron, "traceback": traceback.format_exc()})

        logger.info("CRON", f"Scheduled {len(self.scheduled_jobs)} tasks successfully")
        self._log_next_run_times()

    def _schedule_single_task(self, idx, cron):
        """Schedule a single cron task with detailed logging"""
        logger.debug("CRON", f"Processing cron job {idx}", {"config": cron})

        # Determine timezone
        if 'timezone' in cron and cron['timezone']:
            try:
                local_tz = pytz.timezone(cron['timezone'])
                logger.debug("CRON", f"Using specified timezone: {cron['timezone']}")
            except pytz.UnknownTimeZoneError:
                logger.warning("CRON", f"Unknown timezone '{cron['timezone']}', using default {self.default_tz}")
                local_tz = self.default_tz
        else:
            local_tz = self.default_tz
            logger.debug("CRON", f"No timezone specified, using default: {local_tz}")

        local_tz_str = local_tz.zone if isinstance(local_tz, pytz.BaseTzInfo) else str(local_tz)

        # Parse quantity
        try:
            qty = int(cron['qty']) if cron['qty'] else 1
        except (ValueError, TypeError):
            qty = 1
            logger.warning("CRON", f"Invalid qty '{cron.get('qty')}' for job {idx}, using default: 1")

        # Validate 'every' field
        if 'every' not in cron or not hasattr(schedule.every(qty), cron['every']):
            logger.error("CRON", f"Invalid 'every' field for job {idx}", {"cron": cron})
            return

        # Create schedule
        every_method = getattr(schedule.every(qty), cron['every'])

        # Wrap the CLI call with logging
        def logged_cli_call(args):
            job_start = datetime.now()
            logger.info("CRON", f"Executing scheduled job {idx}", {"args": args})
            try:
                result = main_cli(args)
                elapsed = (datetime.now() - job_start).total_seconds()
                logger.info("CRON", f"Job {idx} completed in {elapsed:.2f}s",
                            {"result": result, "args": args})
            except Exception as e:
                elapsed = (datetime.now() - job_start).total_seconds()
                logger.error("CRON", f"Job {idx} failed after {elapsed:.2f}s",
                             {"error": str(e), "args": args, "traceback": traceback.format_exc()})

        # Schedule with 'at' time if specified
        if cron.get('at'):
            if re.match(r'^\d{2}:\d{2}$', cron['at']):
                job = every_method.at(cron['at'], local_tz_str).do(logged_cli_call, cron['do'])
                logger.info("CRON", f"Scheduled job {idx} at {cron['at']} {local_tz_str}",
                            {"command": cron['do'], "frequency": f"{qty} {cron['every']}"})
                self.scheduled_jobs.append((idx, job, cron))
            else:
                logger.error("CRON", f"Invalid time format '{cron['at']}' for job {idx}")
        else:
            job = every_method.do(logged_cli_call, cron['do'])
            logger.info("CRON", f"Scheduled job {idx} every {qty} {cron['every']}",
                        {"command": cron['do']})
            self.scheduled_jobs.append((idx, job, cron))

    def _log_next_run_times(self):
        """Log next run times for all scheduled jobs"""
        logger.info("CRON", "Next scheduled run times:")
        for idx, job, cron in self.scheduled_jobs:
            next_run = job.next_run.strftime('%Y-%m-%d %H:%M:%S') if job.next_run else "Not scheduled"
            logger.info("CRON", f"  Job {idx}: {next_run} - {cron['do']}")

    def watch_config(self):
        """Watch configuration file for changes with logging"""
        event_handler = ConfigChangeHandler(config_path, callback=self.schedule_tasks)

        try:
            self.observer.schedule(event_handler, path=os.path.dirname(config_path), recursive=False)
            self.observer.start()
            logger.info("CRON", f"Started watching {config_path} for changes")
        except Exception as e:
            logger.error("CRON", f"Failed to start config watcher: {str(e)}")
            return

        try:
            while not self.stop_event.is_set():
                # Run pending scheduled jobs
                pending_jobs = schedule.get_jobs()
                if pending_jobs:
                    logger.debug("CRON", f"Checking {len(pending_jobs)} pending jobs")

                schedule.run_pending()

                # Log scheduler status every 5 minutes
                if hasattr(self, '_last_status_log'):
                    if (datetime.now() - self._last_status_log).total_seconds() > 300:
                        self._log_scheduler_status()
                else:
                    self._last_status_log = datetime.now()

                # Wait for next check
                self.stop_event.wait(60)

        except KeyboardInterrupt:
            logger.warning("CRON", "Scheduler interrupted by user")
        except Exception as e:
            logger.error("CRON", f"Scheduler error: {str(e)}",
                         {"traceback": traceback.format_exc()})
        finally:
            logger.info("CRON", "Stopping config watcher")
            self.observer.stop()
            self.observer.join()

    def _log_scheduler_status(self):
        """Log current scheduler status"""
        self._last_status_log = datetime.now()
        jobs = schedule.get_jobs()
        logger.info("CRON", f"Scheduler status: {len(jobs)} active jobs")

        # Log jobs that will run in the next hour
        upcoming = []
        for job in jobs:
            if job.next_run and (job.next_run - datetime.now()).total_seconds() < 3600:
                upcoming.append(job)

        if upcoming:
            logger.info("CRON", f"{len(upcoming)} jobs scheduled to run in the next hour")


class ConfigChangeHandler(FileSystemEventHandler):
    def __init__(self, file_path, callback):
        self.file_path = file_path
        self.callback = callback
        self.last_hash = calculate_hash(file_path)
        self.last_modified = time.time()
        logger.debug("CONFIG_WATCHER", f"Initialized for {file_path}")

    def on_modified(self, event):
        """Handle file modification events with debouncing"""
        if event.event_type == 'modified' and event.src_path == self.file_path:
            # Debounce rapid modifications
            current_time = time.time()
            if current_time - self.last_modified < 1:
                logger.debug("CONFIG_WATCHER", "Ignoring rapid modification event")
                return

            self.last_modified = current_time
            new_hash = calculate_hash(self.file_path)

            if new_hash != self.last_hash:
                logger.info("CONFIG_WATCHER", f"Configuration file modified",
                            {"old_hash": self.last_hash[:8] if self.last_hash else None,
                             "new_hash": new_hash[:8] if new_hash else None})
                self.last_hash = new_hash

                try:
                    self.callback()
                except Exception as e:
                    logger.error("CONFIG_WATCHER", f"Callback failed: {str(e)}",
                                 {"traceback": traceback.format_exc()})
            else:
                logger.debug("CONFIG_WATCHER", "File modified but content unchanged")


# Main entry point for testing
if __name__ == "__main__":
    logger.info("CRON", "Starting cron scheduler in standalone mode")
    stop_event = threading.Event()

    try:
        cron = Cron(stop_event)
        cron.start()

        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("CRON", "Shutting down cron scheduler")
        stop_event.set()
        cron.join(timeout=5)
        logger.info("CRON", "Cron scheduler stopped")