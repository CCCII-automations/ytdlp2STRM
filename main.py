import logging
import sys
import os
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
import socket
import threading
import time

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('flask_debug.log')
    ]
)

# Create separate loggers for different components
app_logger = logging.getLogger('flask_app')
socket_logger = logging.getLogger('socket_handler')
main_logger = logging.getLogger('main')

# Set Flask's logger to DEBUG level
logging.getLogger('werkzeug').setLevel(logging.DEBUG)

app = Flask(__name__)
CORS(app)

# Log Flask configuration
app_logger.info("=" * 50)
app_logger.info("FLASK APP INITIALIZATION STARTED")
app_logger.info(f"Python version: {sys.version}")
app_logger.info(f"Flask version: {Flask.__version__}")
app_logger.info(f"Current working directory: {os.getcwd()}")
app_logger.info(f"__name__: {__name__}")
app_logger.info("=" * 50)


@app.before_request
def log_request_info():
    app_logger.debug(f"Request: {request.method} {request.url}")
    app_logger.debug(f"Headers: {dict(request.headers)}")


@app.after_request
def log_response_info(response):
    app_logger.debug(f"Response: {response.status}")
    return response


@app.route('/')
def home():
    app_logger.info("Home route accessed")
    return jsonify({
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "message": "Flask app is working"
    })


@app.route('/health')
def health():
    app_logger.info("Health check route accessed")
    return jsonify({"status": "healthy"})


def check_port_availability(port):
    """Check if a port is available before binding"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('', port))
        sock.close()
        app_logger.info(f"Port {port} is available")
        return True
    except OSError as e:
        app_logger.error(f"Port {port} is not available: {e}")
        return False


def run_flask_app(host='0.0.0.0', port=5000, debug=True):
    """Run Flask app with extensive logging"""
    main_logger.info("=" * 50)
    main_logger.info("ATTEMPTING TO START FLASK APP")
    main_logger.info(f"Host: {host}, Port: {port}, Debug: {debug}")
    main_logger.info("=" * 50)

    # Check if port is available
    if not check_port_availability(port):
        main_logger.error(f"Cannot start Flask app - port {port} is already in use")
        # Try to find what's using the port
        try:
            import subprocess
            if sys.platform == "win32":
                cmd = f"netstat -ano | findstr :{port}"
            else:
                cmd = f"lsof -i :{port}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            main_logger.error(f"Port usage info: {result.stdout}")
        except Exception as e:
            main_logger.error(f"Could not check port usage: {e}")
        return False

    try:
        main_logger.info("Starting Flask app.run()...")
        app.run(host=host, port=port, debug=debug, use_reloader=False)
        main_logger.info("Flask app.run() completed")
        return True
    except Exception as e:
        main_logger.error(f"Failed to start Flask app: {type(e).__name__}: {e}")
        main_logger.exception("Full exception traceback:")
        return False


# Socket handling code (if needed)
class SocketHandler:
    def __init__(self, socket_path='/tmp/app_socket'):
        self.socket_path = socket_path
        self.socket = None
        self.running = False
        socket_logger.info(f"SocketHandler initialized with path: {socket_path}")

    def start(self):
        """Start socket listener in a separate thread"""
        try:
            # Remove existing socket file if it exists
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
                socket_logger.info(f"Removed existing socket file: {self.socket_path}")

            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.bind(self.socket_path)
            self.socket.listen(1)
            self.running = True

            socket_logger.info(f"Socket listening on: {self.socket_path}")

            # Start listener thread
            listener_thread = threading.Thread(target=self._listen, daemon=True)
            listener_thread.start()
            socket_logger.info("Socket listener thread started")

        except Exception as e:
            socket_logger.error(f"Failed to start socket: {e}")
            raise

    def _listen(self):
        """Listen for socket connections"""
        while self.running:
            try:
                socket_logger.debug("Waiting for socket connection...")
                conn, addr = self.socket.accept()
                socket_logger.info(f"Socket connection accepted")

                # Handle connection in separate thread
                handler_thread = threading.Thread(
                    target=self._handle_connection,
                    args=(conn,),
                    daemon=True
                )
                handler_thread.start()

            except Exception as e:
                if self.running:
                    socket_logger.error(f"Socket listen error: {e}")

    def _handle_connection(self, conn):
        """Handle individual socket connection"""
        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    break

                message = data.decode('utf-8')
                socket_logger.info(f"Socket received: {message}")

                # Echo back
                response = f"Echo: {message}"
                conn.send(response.encode('utf-8'))

        except Exception as e:
            socket_logger.error(f"Socket connection error: {e}")
        finally:
            conn.close()
            socket_logger.debug("Socket connection closed")

    def stop(self):
        """Stop socket listener"""
        self.running = False
        if self.socket:
            self.socket.close()
            socket_logger.info("Socket closed")


# Main entry point
if __name__ == '__main__':
    main_logger.info("=" * 70)
    main_logger.info("MAIN.PY EXECUTION STARTED")
    main_logger.info("=" * 70)

    # Initialize socket handler if needed
    socket_handler = None
    if '--enable-socket' in sys.argv:
        main_logger.info("Socket mode enabled")
        socket_handler = SocketHandler()
        try:
            socket_handler.start()
        except Exception as e:
            main_logger.error(f"Failed to start socket handler: {e}")
            sys.exit(1)

    # Start Flask app
    success = run_flask_app()

    if not success:
        main_logger.error("Flask app failed to start")
        if socket_handler:
            socket_handler.stop()
        sys.exit(1)

    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        main_logger.info("Shutdown signal received")
        if socket_handler:
            socket_handler.stop()
        main_logger.info("Application shutdown complete")