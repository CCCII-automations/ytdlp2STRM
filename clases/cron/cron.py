#!/usr/bin/env python3
"""
Cron System for YouTube/Twitch Media Processing
This script provides a cron-like scheduler for media processing tasks.

Usage Examples:
    # Run cron scheduler (default mode)
    python cron.py

    # Run cron scheduler with custom config file
    python cron.py --config ./config/custom_crons.json

    # Validate cron configuration without running
    python cron.py --validate

    # Show current cron job status
    python cron.py --status

    # Run in foreground (non-daemon mode)
    python cron.py --foreground

    # Show help
    python cron.py --help

Configuration Format (crons.json):
    [
        {
            "every": "hours",           # minutes, hours, days, weeks
            "qty": "4",                 # quantity (optional, defaults to 1)
            "at": "",                   # specific time HH:MM (optional, empty for interval)
            "timezone": "",             # timezone (optional, uses system default)
            "do": ["--media", "youtube", "--param", "direct"]  # command as array or string
        }
    ]

Examples:
    # Every 4 hours
    {"every": "hours", "qty": "4", "at": "", "timezone": "", "do": ["--media", "youtube", "--param", "direct"]}

    # Daily at 9:30 AM
    {"every": "day", "qty": "1", "at": "09:30", "timezone": "America/New_York", "do": ["--media", "twitch", "--param", "direct"]}

    # Every 30 minutes
    {"every": "minutes", "qty": "30", "at": "", "timezone": "", "do": "youtube_sync"}
"""

import schedule
import time
import threading
import re
from tzlocal import get_localzone  # $ pip install tzlocal
import pytz
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import hashlib
import argparse
import sys
import signal
import json
from pathlib import Path

# Add the root directory to Python path to find modules
root_dir = Path(__file__).resolve().parents[2]  # Go up 2 levels from clases/cron/
sys.path.insert(0, str(root_dir))

# Now import the modules
try:
    from cli import main as main_cli
    from clases.config import config as c
    from clases.log import log as l
except ImportError as e:
    print(f"❌ Error importing required modules: {e}")
    print(f"💡 Make sure you're running this from the ytdlp2STRM directory structure")
    print(f"📁 Current working directory: {os.getcwd()}")
    print(f"🔍 Looking for modules in: {root_dir}")
    sys.exit(1)

# Global variables for signal handling
stop_event = threading.Event()
cron_thread = None


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    l.log('cron', f"Received signal {signum}, shutting down gracefully...")
    stop_event.set()
    if cron_thread and hasattr(cron_thread, 'is_alive') and cron_thread.is_alive():
        if hasattr(cron_thread, 'join'):
            cron_thread.join(timeout=5)
    l.log('cron', "Cron system shutdown complete")
    sys.exit(0)


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    if hasattr(signal, 'SIGINT'):
        signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGHUP') and os.name != 'nt':  # Not available on Windows
        signal.signal(signal.SIGHUP, signal_handler)


# -- LOAD CONFIG AND CHANNELS FILES
# Always use project root directory for config files
project_root = Path(__file__).resolve().parents[2]  # Go up 2 levels from clases/cron/
config_path = os.path.join(project_root, 'config', 'crons.json')


def calculate_hash(file_path):
    """Calculate the hash SHA-256 of the specified file."""
    l.log('cron', f"Calculating hash for file: {file_path}")
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        hash_value = sha256.hexdigest()
        l.log('cron', f"File hash calculated successfully: {hash_value[:16]}...")
        return hash_value
    except FileNotFoundError:
        l.log('cron', f"File not found: {file_path}")
        return None
    except Exception as e:
        l.log('cron', f"Error calculating hash for {file_path}: {str(e)}")
        return None


def load_crons(config_file_path=None):
    """Load cron configuration from file"""
    if config_file_path is None:
        config_file_path = config_path

    l.log('cron', f"Loading cron configuration from: {config_file_path}")
    try:
        crons = c.config(config_file_path).get_config()
        l.log('cron', f"Successfully loaded {len(crons)} cron configurations")
        return crons
    except Exception as e:
        l.log('cron', f"Error loading cron configuration: {str(e)}")
        return []


def validate_cron_file(config_file_path):
    """Validate cron configuration file without running"""
    l.log('cron', f"Validating cron configuration file: {config_file_path}")

    if not os.path.exists(config_file_path):
        print(f"❌ Configuration file not found: {config_file_path}")
        return False

    try:
        with open(config_file_path, 'r') as f:
            crons = json.load(f)

        if not isinstance(crons, list):
            print("❌ Configuration must be a JSON array")
            return False

        valid_count = 0
        for i, cron_config in enumerate(crons):
            print(f"\n📋 Validating cron job #{i + 1}:")

            # Check required fields
            if 'do' not in cron_config or 'every' not in cron_config:
                print(f"   ❌ Missing required fields ('do' and 'every')")
                continue

            print(f"   ✅ Command: {cron_config['do']}")
            print(f"   ✅ Schedule: every {cron_config.get('qty', 1)} {cron_config['every']}")

            # Check time format
            if cron_config.get('at'):
                if re.match(r'^\d{2}:\d{2}$', cron_config['at']):
                    print(f"   ✅ Time: {cron_config['at']}")
                else:
                    print(f"   ❌ Invalid time format: {cron_config['at']}")
                    continue

            # Check timezone
            if cron_config.get('timezone'):
                try:
                    pytz.timezone(cron_config['timezone'])
                    print(f"   ✅ Timezone: {cron_config['timezone']}")
                except pytz.UnknownTimeZoneError:
                    print(f"   ❌ Invalid timezone: {cron_config['timezone']}")
                    continue

            valid_count += 1
            print(f"   ✅ Cron job #{i + 1} is valid")

        print(f"\n📊 Validation Summary: {valid_count}/{len(crons)} cron jobs are valid")
        return valid_count == len(crons)

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON format: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Error validating configuration: {str(e)}")
        return False


def get_cron_status():
    """Get current status of cron jobs"""
    jobs = schedule.get_jobs()
    status = {
        'total_jobs': len(jobs),
        'jobs': []
    }

    for job in jobs:
        job_info = {
            'next_run': str(job.next_run),
            'interval': str(job.interval),
            'job_func': str(job.job_func)
        }
        status['jobs'].append(job_info)

    l.log('cron', f"Cron status retrieved: {status['total_jobs']} jobs")
    return status


def print_cron_status():
    """Print current cron status to console"""
    status = get_cron_status()

    print(f"\n📊 Cron System Status")
    print(f"=" * 50)
    print(f"Total Jobs: {status['total_jobs']}")

    if status['total_jobs'] == 0:
        print("❌ No cron jobs scheduled")
        return

    print(f"\n📋 Scheduled Jobs:")
    for i, job in enumerate(status['jobs'], 1):
        print(f"   {i}. Next Run: {job['next_run']}")
        print(f"      Interval: {job['interval']}")
        print(f"      Function: {job['job_func']}")
        print()


class Cron(threading.Thread):
    def __init__(self, stop_event, config_file_path=None):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.observer = Observer()
        self.config_hash = None
        self.default_tz = None
        self.config_file_path = config_file_path or config_path
        l.log('cron', f"Cron thread initialized with config: {self.config_file_path}")

    def run(self):
        """Main run method - entry point for cron thread"""
        l.log('cron', "Starting cron thread execution")
        self.initialize_timezone()
        # Pass is_first_run=True to execute jobs immediately
        self.schedule_tasks(is_first_run=True)
        self.watch_config()

    def initialize_timezone(self):
        """Initialize default timezone"""
        l.log('cron', "Initializing default timezone")
        self.default_tz = get_localzone()
        l.log('cron', f"Default timezone set to: {self.default_tz}")

    def validate_cron_config(self, cron_config):
        """Validate individual cron configuration"""
        l.log('cron', f"Validating cron config: {cron_config.get('do', 'unknown')}")

        # Check required fields
        if 'do' not in cron_config or 'every' not in cron_config:
            l.log('cron', f"Missing required fields in cron config: {cron_config}")
            return False

        l.log('cron', f"Cron config validation passed for: {cron_config['do']}")
        return True

    def get_timezone_for_cron(self, cron_config):
        """Get timezone object for cron configuration"""
        if 'timezone' in cron_config and cron_config['timezone']:
            try:
                local_tz = pytz.timezone(cron_config['timezone'])
                l.log('cron', f"Using configured timezone: {cron_config['timezone']}")
                return local_tz
            except pytz.UnknownTimeZoneError:
                l.log('cron', f"Unknown timezone {cron_config['timezone']}, using default {self.default_tz}")
                return self.default_tz
        else:
            l.log('cron', f"No timezone specified, using default: {self.default_tz}")
            return self.default_tz

    def get_timezone_string(self, local_tz):
        """Get timezone string representation"""
        if isinstance(local_tz, pytz.BaseTzInfo):
            return local_tz.zone
        return str(local_tz)

    def validate_quantity(self, qty_config):
        """Validate and return quantity parameter"""
        try:
            qty = int(qty_config) if qty_config else 1
            l.log('cron', f"Quantity validated: {qty}")
            return qty
        except ValueError:
            l.log('cron', f"Invalid quantity '{qty_config}', using default value 1")
            return 1

    def validate_time_format(self, time_str):
        """Validate time format (HH:MM) - empty string is valid for interval scheduling"""
        if not time_str or time_str == "":
            l.log('cron', "No specific time set, using interval scheduling")
            return False

        if re.match(r'^\d{2}:\d{2}$', time_str):
            l.log('cron', f"Time format validated: {time_str}")
            return True
        else:
            l.log('cron', f"Invalid time format: {time_str}")
            return False

    def prepare_command(self, do_config):
        """Prepare command for execution - handles both string and array formats"""
        if isinstance(do_config, list):
            l.log('cron', f"Command is array format: {do_config}")
            return do_config
        elif isinstance(do_config, str):
            l.log('cron', f"Command is string format: {do_config}")
            return do_config
        else:
            l.log('cron', f"Invalid command format: {type(do_config)}, converting to string")
            return str(do_config)

    def clear_existing_jobs(self):
        """Clear all existing scheduled jobs"""
        job_count = len(schedule.get_jobs())
        if job_count > 0:
            l.log('cron', f"Clearing {job_count} existing scheduled jobs")
            for job in schedule.get_jobs():
                schedule.cancel_job(job)
        else:
            l.log('cron', "No existing jobs to clear")

    def schedule_single_job(self, cron_config):
        """Schedule a single cron job based on configuration"""
        l.log('cron', f"Scheduling job: {cron_config.get('do', 'unknown')}")

        # Validate configuration
        if not self.validate_cron_config(cron_config):
            return False

        # Get timezone
        local_tz = self.get_timezone_for_cron(cron_config)
        local_tz_str = self.get_timezone_string(local_tz)

        # Validate quantity
        qty = self.validate_quantity(cron_config.get('qty'))

        # Get schedule method
        try:
            every_method = getattr(schedule.every(qty), cron_config['every'])
            l.log('cron', f"Schedule method configured: every {qty} {cron_config['every']}")
        except AttributeError:
            l.log('cron', f"Invalid schedule method: {cron_config['every']}")
            return False

        # Prepare command
        do_command = self.prepare_command(cron_config['do'])

        # Schedule with or without specific time
        at_time = cron_config.get('at', '')
        if at_time and at_time.strip() and self.validate_time_format(at_time):
            return self.schedule_at_time(every_method, do_command, at_time, local_tz_str)
        else:
            return self.schedule_interval(every_method, do_command, qty, cron_config['every'])

    def schedule_at_time(self, every_method, do_command, at_time, local_tz_str):
        """Schedule job at specific time"""
        try:
            if isinstance(do_command, list):
                every_method.at(at_time, local_tz_str).do(main_cli, *do_command)
            else:
                every_method.at(at_time, local_tz_str).do(main_cli, do_command)
            l.log('cron', f"Scheduled task {do_command} at {at_time} {local_tz_str}")
            return True
        except Exception as e:
            l.log('cron', f"Error scheduling timed job: {str(e)}")
            return False

    def schedule_interval(self, every_method, do_command, qty, every_unit):
        """Schedule job at interval"""
        try:
            if isinstance(do_command, list):
                every_method.do(main_cli, *do_command)
            else:
                every_method.do(main_cli, do_command)
            l.log('cron', f"Scheduled task {do_command} every {qty} {every_unit}")
            return True
        except Exception as e:
            l.log('cron', f"Error scheduling interval job: {str(e)}")
            return False

    def schedule_tasks(self, is_first_run=False):
        """Schedule all tasks from configuration"""
        l.log('cron', "Starting task scheduling process")

        # Check if configuration has changed
        new_hash = calculate_hash(self.config_file_path)
        if self.config_hash == new_hash:
            l.log('cron', "Configuration unchanged, skipping scheduling")
            return

        l.log('cron', "Configuration changed, reloading schedule")
        self.config_hash = new_hash

        # Load configuration
        crons = load_crons(self.config_file_path)
        if not crons:
            l.log('cron', "No cron configurations found")
            return

        l.log('cron', "Scheduling tasks according to the latest crons configuration")

        # Clear existing jobs
        self.clear_existing_jobs()

        # Schedule new jobs
        successful_jobs = 0
        failed_jobs = 0

        for cron_config in crons:
            if self.schedule_single_job(cron_config):
                successful_jobs += 1
            else:
                failed_jobs += 1

        l.log('cron', f"Scheduling complete: {successful_jobs} successful, {failed_jobs} failed")

    def watch_config(self):
        """Watch configuration file for changes and run execution loop"""
        l.log('cron', "Setting up configuration file watcher")

        try:
            event_handler = ConfigChangeHandler(self.config_file_path, callback=self.schedule_tasks)
            self.observer.schedule(event_handler, path=os.path.dirname(self.config_file_path), recursive=False)
            self.observer.start()
            l.log('cron', f"Started watching {self.config_file_path} for changes")
        except Exception as e:
            l.log('cron', f"Error setting up config watcher: {str(e)}")

        # Run execution loop
        self.run_execution_loop()

    def run_execution_loop(self):
        """Main execution loop for running scheduled tasks"""
        l.log('cron', "Starting cron execution loop")

        try:
            while not self.stop_event.is_set():
                self.check_and_run_pending()
                self.stop_event.wait(60)
        except KeyboardInterrupt:
            l.log('cron', "Cron execution interrupted by user")
        except Exception as e:
            l.log('cron', f"Error in execution loop: {str(e)}")
        finally:
            self.cleanup_resources()

        l.log('cron', "Cron execution loop stopped")

    def check_and_run_pending(self):
        """Check and run any pending scheduled jobs"""
        pending_jobs = schedule.get_jobs()
        if pending_jobs:
            l.log('cron', f"Checking {len(pending_jobs)} scheduled jobs")

        try:
            schedule.run_pending()
        except Exception as e:
            l.log('cron', f"Error running pending jobs: {str(e)}")

    def cleanup_resources(self):
        """Clean up resources"""
        l.log('cron', "Cleaning up cron resources")
        if self.observer:
            self.observer.stop()
            self.observer.join()
        l.log('cron', "Cron cleanup completed")


class ConfigChangeHandler(FileSystemEventHandler):
    """Handles file system events for configuration changes"""

    def __init__(self, file_path, callback):
        self.file_path = file_path
        self.callback = callback
        self.last_hash = calculate_hash(file_path)
        l.log('cron', f"Config change handler initialized for: {file_path}")

    def on_modified(self, event):
        """Handle file modification events"""
        if event.event_type == 'modified' and event.src_path == self.file_path:
            l.log('cron', f"Configuration file modified: {self.file_path}")
            new_hash = calculate_hash(self.file_path)

            if new_hash != self.last_hash:
                l.log('cron', "File hash changed, triggering configuration reload")
                self.last_hash = new_hash
                self.callback()
            else:
                l.log('cron', "File modification detected but hash unchanged, ignoring")


def main():
    """Main entry point for command line execution"""
    parser = argparse.ArgumentParser(
        description='Cron System for YouTube/Twitch Media Processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run cron scheduler (default)
    python cron.py

    # Use custom config file
    python cron.py --config ./config/my_crons.json

    # Validate configuration
    python cron.py --validate

    # Show current status
    python cron.py --status
        """
    )

    parser.add_argument('--config', '-c',
                        default=os.path.join(project_root, 'config', 'crons.json'),
                        help='Path to cron configuration file (default: PROJECT_ROOT/config/crons.json)')

    parser.add_argument('--validate', '-v',
                        action='store_true',
                        help='Validate cron configuration without running')

    parser.add_argument('--status', '-s',
                        action='store_true',
                        help='Show current cron job status')

    parser.add_argument('--foreground', '-f',
                        action='store_true',
                        help='Run in foreground (non-daemon mode)')

    args = parser.parse_args()

    # Resolve config file path
    config_file_path = os.path.abspath(args.config)

    # Handle different modes
    if args.validate:
        print(f"🔍 Validating cron configuration: {config_file_path}")
        if validate_cron_file(config_file_path):
            print("✅ Configuration is valid!")
            sys.exit(0)
        else:
            print("❌ Configuration has errors!")
            sys.exit(1)

    if args.status:
        print_cron_status()
        sys.exit(0)

    # Check if config file exists
    if not os.path.exists(config_file_path):
        print(f"❌ Configuration file not found: {config_file_path}")
        print(f"💡 Create a configuration file with this format:")
        print(f"📁 Expected location: {os.path.join(project_root, 'config', 'crons.json')}")
        print("""
[
    {
        "every": "hours",
        "qty": "4",
        "at": "",
        "timezone": "",
        "do": ["--media", "youtube", "--param", "direct"]
    }
]
        """)
        sys.exit(1)

    # Setup signal handlers for graceful shutdown
    setup_signal_handlers()

    # Start cron system
    print(f"🚀 Starting Cron System")
    print(f"📁 Config file: {config_file_path}")
    print(f"🔄 Mode: {'Foreground' if args.foreground else 'Background'}")
    print(f"⏹️  Press Ctrl+C to stop")
    print("-" * 50)

    global cron_thread
    try:
        # Create and start cron thread
        cron_thread = Cron(stop_event, config_file_path)
        if args.foreground:
            cron_thread.daemon = False
        cron_thread.start()

        l.log('cron', "Cron system started successfully")

        # Keep main thread alive
        while not stop_event.is_set():
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break

    except Exception as e:
        l.log('cron', f"Error starting cron system: {str(e)}")
        print(f"❌ Error: {str(e)}")
        sys.exit(1)
    finally:
        signal_handler(signal.SIGTERM, None)


if __name__ == "__main__":
    main()