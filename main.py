# =============================================================================
# FIXED main.py - Single SocketIO instance and proper route registration
# =============================================================================

import signal
import time
import logging
import sys
import os
import json
from threading import Thread, Event
from flask import Flask, request

# Enhanced logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/ytdlp2strm_debug.log')
    ]
)

# Create logger
logger = logging.getLogger(__name__)

# Log startup info
logger.info("=" * 60)
logger.info("ytdlp2STRM Starting...")
logger.info(f"Python version: {sys.version}")
logger.info(f"Current directory: {os.getcwd()}")
logger.info(f"Script location: {os.path.abspath(__file__)}")
logger.info("=" * 60)

# Check if required directories exist
ui_html_path = os.path.join(os.path.dirname(__file__), 'ui/html')
ui_static_path = os.path.join(os.path.dirname(__file__), 'ui/static')
config_path = os.path.join(os.path.dirname(__file__), 'config')
logs_path = os.path.join(os.path.dirname(__file__), 'logs')

logger.info(f"Checking directories:")
logger.info(f"  HTML template dir: {ui_html_path} - Exists: {os.path.exists(ui_html_path)}")
logger.info(f"  Static files dir: {ui_static_path} - Exists: {os.path.exists(ui_static_path)}")
logger.info(f"  Config dir: {config_path} - Exists: {os.path.exists(config_path)}")
logger.info(f"  Logs dir: {logs_path} - Exists: {os.path.exists(logs_path)}")

# Ensure required directories exist
os.makedirs(ui_html_path, exist_ok=True)
os.makedirs(ui_static_path, exist_ok=True)
os.makedirs(config_path, exist_ok=True)
os.makedirs(logs_path, exist_ok=True)

if os.path.exists(ui_html_path):
    logger.info(f"  HTML files: {os.listdir(ui_html_path)}")
if os.path.exists(ui_static_path):
    logger.info(f"  Static files: {os.listdir(ui_static_path)}")


def load_or_create_config():
    """Load configuration or create default if missing"""
    config_file = './config/config.json'

    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            logger.info("✓ Configuration loaded from config.json")
            return config
    except FileNotFoundError:
        logger.warning("Config file not found, creating default configuration...")
        return create_default_config()
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        logger.warning("Creating backup and new default configuration...")

        # Backup corrupted file
        import shutil
        backup_file = f'{config_file}.backup.{int(time.time())}'
        shutil.copy2(config_file, backup_file)
        logger.info(f"Corrupted config backed up to: {backup_file}")

        return create_default_config()


def create_default_config():
    """Create default configuration with authentication"""
    import secrets

    default_config = {
        # Existing ytdlp2strm settings
        "ytdlp2strm_host": "0.0.0.0",
        "ytdlp2strm_port": 5000,
        "ytdlp2strm_keep_old_strm": "True",
        "ytdlp2strm_temp_file_duration": 86400,
        "cookies": "none",
        "cookie_value": "",
        "log_level": "INFO",

        # Authentication settings
        "app_secret_key": secrets.token_hex(32),
        "auth_max_attempts": 5,
        "auth_lockout_time": 300,
        "auth_captcha_threshold": 3,
        "auth_base_delay": 2000,
        "auth_session_timeout": 7200,
        "auth_enable_captcha": True,
        "auth_log_events": True,

        # Default users - passwords will be hashed by AuthManager
        "admins": {
            "admin": {
                "password": "password123",  # Will be hashed automatically
                "role": "admin",
                "created": time.time(),
                "description": "Default administrator account"
            }
        },
        "users": {
            "user": {
                "password": "userpass",  # Will be hashed automatically
                "role": "user",
                "created": time.time(),
                "description": "Default user account"
            }
        }
    }

    # Save default config
    config_file = './config/config.json'
    try:
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        logger.info(f"✓ Default configuration saved to {config_file}")
        logger.warning("⚠ Using default credentials - change them immediately!")
        logger.warning("   Admin: admin / password123")
        logger.warning("   User: user / userpass")
    except Exception as e:
        logger.error(f"Failed to save default configuration: {e}")

    return default_config


# Load configuration early
app_config = load_or_create_config()

# Initialize Flask with error handling and SECRET KEY
try:
    app = Flask(__name__,
                template_folder='ui/html',
                static_folder='ui/static',
                static_url_path='')

    # SET SECRET KEY IMMEDIATELY - This fixes the RuntimeError
    secret_key = app_config.get('app_secret_key')
    if secret_key:
        app.secret_key = secret_key
        logger.info("✓ Secret key loaded from configuration")
    else:
        # Generate emergency secret key
        import secrets

        emergency_key = secrets.token_hex(32)
        app.secret_key = emergency_key
        logger.warning("⚠ Using emergency generated secret key")
        logger.warning("  Add 'app_secret_key' to your config.json file")

    # Configure session settings for security
    from datetime import timedelta

    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=app_config.get('auth_session_timeout', 7200)),
        SESSION_COOKIE_SECURE=False,  # Set to True with HTTPS
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax'
    )

    logger.info("✓ Flask app initialized successfully")
    logger.info(f"  Template folder: {app.template_folder}")
    logger.info(f"  Static folder: {app.static_folder}")
    logger.info(f"  Static URL path: {app.static_url_path}")
    logger.info(f"  Secret key set: {'Yes' if app.secret_key else 'No'}")
    logger.info(f"  Secret key length: {len(app.secret_key) if app.secret_key else 0}")

except Exception as e:
    logger.error(f"Failed to initialize Flask app: {e}")
    sys.exit(1)

# Initialize SocketIO ONCE here
from flask_socketio import SocketIO

socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)
logger.info("✓ SocketIO initialized")

# Import custom modules with error handling
try:
    from clases.config import config as c

    logger.info("✓ Imported clases.config")
except ImportError as e:
    logger.error(f"Failed to import clases.config: {e}")
    c = None

try:
    from clases.folders import folders as f

    logger.info("✓ Imported clases.folders")
except ImportError as e:
    logger.error(f"Failed to import clases.folders: {e}")
    f = None

try:
    from clases.log import log as l

    logger.info("✓ Imported clases.log")
except ImportError as e:
    logger.error(f"Failed to import clases.log: {e}")


    # Fallback logging
    class FallbackLog:
        def log(self, module, message):
            logger.info(f"[{module}] {message}")


    l = FallbackLog()

try:
    from clases.cron import cron as cron

    logger.info("✓ Imported clases.cron")
except ImportError as e:
    logger.error(f"Failed to import clases.cron: {e}")
    cron = None

# Import UI components BEFORE routes
try:
    from ui.ui import Ui
    from ui.auth import auth_manager, requires_auth, requires_admin

    logger.info("✓ Imported UI components")
except ImportError as e:
    logger.error(f"Failed to import UI components: {e}")
    sys.exit(1)

# Create single UI instance
_ui = Ui()
logger.info("✓ UI instance created")

# Store to prevent duplicate command executions
_command_executions = {}


# Import and define SocketIO handlers ONCE
@socketio.on('execute_command')
def handle_command(command):
    """Handle command execution with duplicate prevention"""
    from flask import session

    # Add authentication check for socket.io commands
    if 'authenticated' not in session or not session['authenticated']:
        socketio.emit('command_error', 'Authentication required')
        return

    # Prevent duplicate commands
    current_time = time.time()
    command_hash = hash(command)

    # Check if this exact command was executed very recently (within 2 seconds)
    if command_hash in _command_executions:
        last_execution = _command_executions[command_hash]
        if current_time - last_execution < 2.0:
            l.log("socketio", f"Ignoring duplicate command execution: {command}")
            return

    # Record this execution
    _command_executions[command_hash] = current_time

    # Clean old entries (keep only last 10 commands)
    if len(_command_executions) > 10:
        oldest_hash = min(_command_executions.keys(),
                          key=lambda h: _command_executions[h])
        del _command_executions[oldest_hash]

    l.log("socketio", f"Executing command: {command}")

    # Execute the command
    _ui.handle_command(command)


@socketio.on('connect')
def handle_connect():
    from flask import session
    logger.info(f"Client connected: {session.get('username', 'anonymous')}")


@socketio.on('disconnect')
def handle_disconnect():
    from flask import session
    logger.info(f"Client disconnected: {session.get('username', 'anonymous')}")


# Import routes AFTER SocketIO is initialized
try:
    logger.info("Registering routes...")

    # Import Flask modules
    from flask import render_template, request, session, jsonify, url_for, redirect
    import bcrypt
    import ipaddress


    # Register individual routes instead of importing routes.py
    # This avoids the multiple SocketIO issue

    @app.route('/')
    @requires_auth
    def index():
        crons = _ui.crons
        return render_template(
            'index.html',
            plugins=_ui.plugins,
            crons=crons
        )


    @app.route('/api/update-plugins', methods=['POST'])
    def api_update_plugins():
        try:
            data = request.get_json()
            changes = data.get('changes', [])

            # Read current plugins.py content
            current_content = _ui.plugins_py
            lines = current_content.split('\n')

            # Apply changes
            for change in changes:
                plugin_name = change['name']
                should_enable = change['enabled']

                # Find and update the plugin line
                for i, line in enumerate(lines):
                    original_line = line.strip()

                    # Check if this line is for our plugin
                    is_our_plugin = False

                    # Handle both import formats
                    if f'from plugins.{plugin_name} import' in line or f'import plugins.{plugin_name}' in line:
                        is_our_plugin = True

                    if is_our_plugin:
                        if should_enable and line.strip().startswith('#'):
                            # Enable plugin (remove #)
                            hash_pos = line.find('#')
                            if hash_pos != -1:
                                lines[i] = line[:hash_pos] + line[hash_pos + 1:].lstrip()
                        elif not should_enable and not line.strip().startswith('#'):
                            # Disable plugin (add #)
                            leading_spaces = len(line) - len(line.lstrip())
                            lines[i] = line[:leading_spaces] + '#' + line[leading_spaces:]
                        break

            # Save updated content
            _ui.plugins_py = '\n'.join(lines)

            return jsonify({'success': True, 'message': 'Plugins updated successfully'})

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/status', methods=['GET'])
    def api_status():
        try:
            plugins = _ui.plugins
            crons = _ui.crons

            # Calculate statistics
            total_plugins = len(plugins)
            active_plugins = len([p for p in plugins if p.get('enabled', False)])
            total_channels = sum(len(p.get('channels', [])) for p in plugins if p.get('channels'))
            total_crons = len(crons)

            return jsonify({
                'success': True,
                'stats': {
                    'total_plugins': total_plugins,
                    'active_plugins': active_plugins,
                    'total_channels': total_channels,
                    'total_crons': total_crons
                },
                'plugins': plugins,
                'crons': crons
            })

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    # Add other essential routes here...
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Basic login route"""
        if request.method == 'GET':
            return render_template('login.html')
        # Handle POST login logic here
        return jsonify({'success': False, 'message': 'Login not implemented'})


    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))


    logger.info("✓ Essential routes registered")

except Exception as e:
    logger.error(f"Failed to register routes: {e}")
    logger.exception("Route registration error:")


# Add debug route to check app status
@app.route('/debug/config')
def debug_config():
    """Debug endpoint to check configuration"""
    return {
        'working_directory': os.getcwd(),
        'template_folder': app.template_folder,
        'static_folder': app.static_folder,
        'static_url_path': app.static_url_path,
        'registered_routes': [str(rule) for rule in app.url_map.iter_rules()],
        'config_loaded': c is not None,
        'folders_loaded': f is not None,
        'log_loaded': l is not None,
        'cron_loaded': cron is not None,
        'secret_key_set': bool(app.secret_key),
        'secret_key_length': len(app.secret_key) if app.secret_key else 0,
        'socketio_initialized': socketio is not None,
        'session_config': {
            'lifetime': str(app.config.get('PERMANENT_SESSION_LIFETIME')),
            'secure': app.config.get('SESSION_COOKIE_SECURE'),
            'httponly': app.config.get('SESSION_COOKIE_HTTPONLY'),
            'samesite': app.config.get('SESSION_COOKIE_SAMESITE')
        }
    }


def run_flask_app(stop_event, port):
    @app.before_request
    def before_request():
        # Log all incoming requests
        logger.debug(f"Request: {request.method} {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")

        if stop_event.is_set():
            log_text = ("Shutting down Flask server...")
            l.log("main", log_text)

            func = request.environ.get('werkzeug.server.shutdown')
            if func:
                func()

    try:
        logger.info(f"Starting Flask app on {host}:{port}")
        logger.info(f"Secret key status: {'SET' if app.secret_key else 'NOT SET'}")
        # Use socketio.run instead of app.run for SocketIO support
        socketio.run(app, host=host, port=port, debug=False, use_reloader=False)
    except Exception as e:
        log_text = (f"Exception in Flask app: {e}")
        l.log("main", log_text)
        logger.exception("Flask app exception:")

    log_text = ("Flask app stopped.")
    l.log("main", log_text)


def signal_handler(sig, frame):
    log_text = ('Signal received, terminating threads...')
    l.log("main", log_text)

    stop_event.set()

    log_text = ('Threads and process terminated.')
    l.log("main", log_text)
    exit(0)


if __name__ == "__main__":
    # Use the loaded configuration
    try:
        if c:
            ytdlp2strm_config = c.config('./config/config.json').get_config()
            logger.info(f"Configuration loaded via clases.config: {ytdlp2strm_config}")
        else:
            logger.warning("Using direct configuration (clases.config not available)")
            ytdlp2strm_config = app_config
    except Exception as e:
        logger.error(f"Failed to load configuration via clases.config: {e}")
        ytdlp2strm_config = app_config

    stop_event = Event()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start Cron if available
    if cron:
        try:
            crons = cron.Cron(stop_event)
            crons.start()
            log_text = (" * Crons thread started")
            l.log("main", log_text)
        except Exception as e:
            logger.error(f"Failed to start cron: {e}")
    else:
        logger.warning("Cron module not available, skipping cron tasks")

    # Start Folders cleanup if available
    if f:
        try:
            folders_instance = f.Folders()
            thread_clean_old_videos = Thread(target=folders_instance.clean_old_videos, args=(stop_event,))
            thread_clean_old_videos.daemon = True
            thread_clean_old_videos.start()
            log_text = (" * Clean old videos thread started")
            l.log("main", log_text)
        except Exception as e:
            logger.error(f"Failed to start folders cleanup: {e}")
    else:
        logger.warning("Folders module not available, skipping cleanup tasks")

    # Start Flask app with SocketIO
    port = ytdlp2strm_config.get('ytdlp2strm_port', 5000)
    host = ytdlp2strm_config.get('ytdlp2strm_host', '0.0.0.0')
    logger.info(f"Starting Flask with SocketIO on port {port}")
    logger.info("=" * 60)
    logger.info("APPLICATION STARTUP COMPLETE")
    logger.info(f"🌐 Web Interface: http://{host}:{port}")
    logger.info(f"🔐 Login URL: http://{host}:{port}/login")
    logger.info(f"🛠️ Debug Config: http://{host}:{port}/debug/config")
    logger.info("=" * 60)

    flask_thread = Thread(target=run_flask_app, args=(stop_event, port))
    flask_thread.daemon = True
    flask_thread.start()
    log_text = (" * Flask with SocketIO thread started")
    l.log("main", log_text)

    try:
        logger.info("Main thread running, press Ctrl+C to stop")
        while not stop_event.is_set():
            time.sleep(1)

        log_text = ('Threads and process terminated.')
        l.log("main", log_text)

    except Exception as e:
        log_text = (f"Exception in main loop: {e}")
        l.log("main", log_text)
        logger.exception("Main loop exception:")

    log_text = ("Exiting main.")
    l.log("main", log_text)