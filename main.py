import signal
import time
import logging
import sys
import os
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

logger.info(f"Checking UI directories:")
logger.info(f"  HTML template dir: {ui_html_path} - Exists: {os.path.exists(ui_html_path)}")
logger.info(f"  Static files dir: {ui_static_path} - Exists: {os.path.exists(ui_static_path)}")

if os.path.exists(ui_html_path):
    logger.info(f"  HTML files: {os.listdir(ui_html_path)}")
if os.path.exists(ui_static_path):
    logger.info(f"  Static files: {os.listdir(ui_static_path)}")

# Initialize Flask with error handling
try:
    app = Flask(__name__,
                template_folder='ui/html',
                static_folder='ui/static',
                static_url_path='')
    logger.info("Flask app initialized successfully")
    logger.info(f"  Template folder: {app.template_folder}")
    logger.info(f"  Static folder: {app.static_folder}")
    logger.info(f"  Static URL path: {app.static_url_path}")
except Exception as e:
    logger.error(f"Failed to initialize Flask app: {e}")
    sys.exit(1)

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

# Import routes with detailed error handling
try:
    logger.info("Attempting to import config.routes...")
    import config.routes

    logger.info("✓ Successfully imported config.routes")

    # Log registered routes
    logger.info("Registered Flask routes:")
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        logger.info(f"  {rule.endpoint:30s} {methods:10s} {rule.rule}")

except ImportError as e:
    logger.error(f"Failed to import config.routes: {e}")
    logger.error("Routes will not be available!")


    # Add a debug route to help diagnose
    @app.route('/')
    def debug_home():
        return f"""
        <h1>ytdlp2STRM Debug Mode</h1>
        <p>Routes module failed to load: {str(e)}</p>
        <p>Template folder: {app.template_folder}</p>
        <p>Static folder: {app.static_folder}</p>
        <p>Check the logs for more details.</p>
        """


# Add debug route to check app status
@app.route('/debug/status')
def debug_status():
    """Debug endpoint to check app configuration"""
    import json
    return json.dumps({
        'working_directory': os.getcwd(),
        'template_folder': app.template_folder,
        'static_folder': app.static_folder,
        'static_url_path': app.static_url_path,
        'registered_routes': [str(rule) for rule in app.url_map.iter_rules()],
        'config_loaded': c is not None,
        'folders_loaded': f is not None,
        'log_loaded': l is not None,
        'cron_loaded': cron is not None
    }, indent=2)


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
        logger.info(f"Starting Flask app on 0.0.0.0:{port}")
        app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
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
    # Load configuration with error handling
    try:
        if c:
            ytdlp2strm_config = c.config('./config/config.json').get_config()
            logger.info(f"Configuration loaded: {ytdlp2strm_config}")
        else:
            logger.warning("Using default configuration (config module not loaded)")
            ytdlp2strm_config = {'ytdlp2strm_port': 5000}
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        ytdlp2strm_config = {'ytdlp2strm_port': 5000}

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

    # Start Flask app
    port = ytdlp2strm_config.get('ytdlp2strm_port', 5000)
    logger.info(f"Starting Flask on port {port}")

    flask_thread = Thread(target=run_flask_app, args=(stop_event, port))
    flask_thread.daemon = True
    flask_thread.start()
    log_text = (" * Flask thread started")
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