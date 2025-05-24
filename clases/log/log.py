import os
import sys
import io
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from flask_socketio import emit

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

# Try to import Enum, with fallback
try:
    from enum import Enum

    ENUM_AVAILABLE = True
except ImportError:
    ENUM_AVAILABLE = False

if ENUM_AVAILABLE:
    class LogLevel(Enum):
        DEBUG = ("DEBUG", "\033[36m")  # Cyan
        INFO = ("INFO", "\033[32m")  # Green
        WARNING = ("WARNING", "\033[33m")  # Yellow
        ERROR = ("ERROR", "\033[31m")  # Red
        CRITICAL = ("CRITICAL", "\033[35m")  # Magenta
        UI = ("UI", "\033[0m")  # No color
else:
    # Fallback class that mimics Enum behavior with proper attribute access
    class LogLevelValue:
        def __init__(self, name, color):
            self.value = (name, color)
            self.name = name

        def __str__(self):
            return self.name


    class LogLevel:
        DEBUG = LogLevelValue("DEBUG", "\033[36m")
        INFO = LogLevelValue("INFO", "\033[32m")
        WARNING = LogLevelValue("WARNING", "\033[33m")
        ERROR = LogLevelValue("ERROR", "\033[31m")
        CRITICAL = LogLevelValue("CRITICAL", "\033[35m")
        UI = LogLevelValue("UI", "\033[0m")


class Logger:
    def __init__(self, log_file: str = 'ytdlp2strm.log', max_days: int = 7,
                 enable_colors: bool = True, min_level: LogLevel = None):
        self.log_file = log_file
        self.max_days = max_days
        self.enable_colors = enable_colors
        # Set default min_level if not provided
        self.min_level = min_level if min_level is not None else LogLevel.DEBUG
        self.cleanup_file = 'log_cleanup.txt'
        self._setup_cleanup()

    def _format_message(self, level: LogLevel, author: str, text: str,
                        extra_data: Optional[Dict[str, Any]] = None) -> str:
        """Format log message with timestamp, level, and optional data"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if level == LogLevel.UI:
            return text.strip()

        # Handle both Enum and LogLevelValue
        if ENUM_AVAILABLE and hasattr(level, 'value'):
            level_str = level.value[0]
        elif hasattr(level, 'value'):
            level_str = level.value[0]
        else:
            level_str = str(level)

        base_msg = f'[{timestamp}] [{level_str}] {author}: {text.strip()}'

        if extra_data:
            extra_str = json.dumps(extra_data, separators=(',', ':'))
            base_msg += f' | {extra_str}'

        return base_msg

    def _colorize(self, message: str, level: LogLevel) -> str:
        """Add colors to console output"""
        if not self.enable_colors:
            return message

        # Handle both Enum and LogLevelValue
        if ENUM_AVAILABLE and hasattr(level, 'value'):
            color = level.value[1]
        elif hasattr(level, 'value'):
            color = level.value[1]
        else:
            # Fallback colors for string levels
            color_map = {
                'DEBUG': '\033[36m',
                'INFO': '\033[32m',
                'WARNING': '\033[33m',
                'ERROR': '\033[31m',
                'CRITICAL': '\033[35m',
                'UI': '\033[0m'
            }
            color = color_map.get(str(level), '\033[0m')

        return f"{color}{message}\033[0m"

    def _should_log(self, level: LogLevel) -> bool:
        """Check if message should be logged based on minimum level"""
        level_order = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING,
                       LogLevel.ERROR, LogLevel.CRITICAL, LogLevel.UI]
        try:
            return level_order.index(level) >= level_order.index(self.min_level)
        except ValueError:
            # If comparison fails, always log
            return True

    def _emit_socketio(self, message: str, level: LogLevel):
        """Emit message via SocketIO if available"""
        try:
            if ENUM_AVAILABLE and hasattr(level, 'value'):
                level_str = level.value[0]
            elif hasattr(level, 'value'):
                level_str = level.value[0]
            else:
                level_str = str(level)

            emit('command_output', {
                'message': message,
                'level': level_str,
                'timestamp': datetime.now().isoformat()
            })
        except Exception:
            self._write_to_file(f"[{datetime.now()}] [WARNING] Logger: SocketIO emit failed")

    def _write_to_file(self, message: str):
        """Write message to log file"""
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except Exception as e:
            print(f"Failed to write to log file: {e}")

    def log(self, level: LogLevel, author: str, text: str,
            extra_data: Optional[Dict[str, Any]] = None,
            emit_socket: bool = True):
        """Main logging method"""
        if not text or not text.strip() or not self._should_log(level):
            return

        message = self._format_message(level, author, text, extra_data)

        # Console output with colors
        colored_msg = self._colorize(message, level)
        print(colored_msg)
        sys.stdout.flush()

        # File output (without colors)
        self._write_to_file(message)

        # SocketIO emission
        if emit_socket:
            self._emit_socketio(message, level)

    # Convenience methods
    def debug(self, author: str, text: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        self.log(LogLevel.DEBUG, author, text, extra_data, **kwargs)

    def info(self, author: str, text: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        self.log(LogLevel.INFO, author, text, extra_data, **kwargs)

    def warning(self, author: str, text: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        self.log(LogLevel.WARNING, author, text, extra_data, **kwargs)

    def error(self, author: str, text: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        self.log(LogLevel.ERROR, author, text, extra_data, **kwargs)

    def critical(self, author: str, text: str, extra_data: Optional[Dict[str, Any]] = None, **kwargs):
        self.log(LogLevel.CRITICAL, author, text, extra_data, **kwargs)

    def ui(self, text: str, **kwargs):
        self.log(LogLevel.UI, "UI", text, emit_socket=kwargs.get('emit_socket', True))

    def command_output(self, command: str, output: str, return_code: int = 0,
                       author: str = "CMD"):
        """Log command execution with formatted output"""
        level = LogLevel.ERROR if return_code != 0 else LogLevel.INFO
        extra_data = {
            'command': command,
            'return_code': return_code,
            'output_lines': len(output.splitlines()) if output else 0
        }

        self.log(level, author, f"Command executed: {command}", extra_data)

        if output:
            for line in output.strip().split('\n'):
                if line.strip():
                    self.log(level, f"{author}_OUT", line.strip())

    def pretty_dict(self, data: Dict[str, Any], title: str = "Data",
                    author: str = "SYSTEM"):
        """Log dictionary data in a pretty format"""
        self.info(author, f"{title}:")
        for key, value in data.items():
            self.info(author, f"  {key}: {value}")

    def progress(self, current: int, total: int, description: str = "",
                 author: str = "PROGRESS"):
        """Log progress information"""
        percentage = (current / total * 100) if total > 0 else 0
        bar_length = 20
        filled_length = int(bar_length * current // total) if total > 0 else 0
        bar = '█' * filled_length + '░' * (bar_length - filled_length)

        msg = f"{description} [{bar}] {current}/{total} ({percentage:.1f}%)"
        self.info(author, msg)

    def _setup_cleanup(self):
        """Setup automatic log cleanup"""
        if self._should_cleanup():
            self._cleanup_old_logs()
            self._update_cleanup_date()

    def _should_cleanup(self) -> bool:
        """Check if cleanup is needed"""
        if not os.path.exists(self.cleanup_file):
            return True

        try:
            with open(self.cleanup_file, 'r', encoding='utf-8') as f:
                last_date = datetime.fromisoformat(f.read().strip()).date()
                return (datetime.now().date() - last_date).days >= 1
        except (ValueError, FileNotFoundError):
            return True

    def _cleanup_old_logs(self):
        """Remove old log entries"""
        if not os.path.exists(self.log_file):
            return

        cutoff = datetime.now() - timedelta(days=self.max_days)
        temp_file = f"{self.log_file}.tmp"

        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as infile, \
                    open(temp_file, 'w', encoding='utf-8') as outfile:

                for line in infile:
                    try:
                        # Extract timestamp from log line
                        if line.startswith('[') and ']' in line:
                            timestamp_str = line.split(']')[0][1:19]  # Get first 19 chars
                            log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

                            if log_time > cutoff:
                                outfile.write(line)
                    except (ValueError, IndexError):
                        continue

            # Replace original file with cleaned version
            os.replace(temp_file, self.log_file)
            self.info("CLEANUP", f"Log cleanup completed, entries older than {self.max_days} days removed")

        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            self.error("CLEANUP", f"Log cleanup failed: {e}")

    def _update_cleanup_date(self):
        """Update the last cleanup date"""
        try:
            os.makedirs(os.path.dirname(self.cleanup_file), exist_ok=True)
            with open(self.cleanup_file, 'w', encoding='utf-8') as f:
                f.write(datetime.now().date().isoformat())
        except Exception as e:
            self.error("CLEANUP", f"Failed to update cleanup date: {e}")


# Backward compatibility - create a function that mimics the old class behavior
def log(author: str, text: str, level: LogLevel = None):
    """Backward compatible logging function"""
    if not hasattr(log, '_logger'):
        log._logger = Logger()

    if level is None:
        level = LogLevel.INFO

    if author == 'ui':
        log._logger.ui(text)
    else:
        log._logger.log(level, author, text)


# Usage examples:
if __name__ == "__main__":
    logger = Logger(min_level=LogLevel.DEBUG, enable_colors=True)

    # Basic logging
    logger.info("APP", "Application started")
    logger.warning("CONFIG", "Configuration file not found, using defaults")
    logger.error("DB", "Database connection failed")

    # Command output
    logger.command_output("ls -la", "total 64\ndrwxr-xr-x  8 user  staff   256 Dec  1 10:30 .", 0)

    # Progress logging
    for i in range(0, 101, 25):
        logger.progress(i, 100, "Processing files")

    # Pretty dictionary
    logger.pretty_dict({"status": "active", "users": 42, "version": "1.0.0"}, "System Status")

    # UI messages
    logger.ui("Welcome to the application!")