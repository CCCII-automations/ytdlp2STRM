#!/usr/bin/env python3
"""
Simplified Flask app for debugging startup issues
"""
import logging
import sys
import os

# Basic logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

logger.info("=" * 50)
logger.info("Starting Flask application")
logger.info(f"Python: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info("=" * 50)

try:
    from flask import Flask, jsonify
    import flask

    logger.info(f"Flask version: {flask.__version__}")
except ImportError as e:
    logger.error(f"Failed to import Flask: {e}")
    sys.exit(1)

try:
    from flask_cors import CORS

    logger.info("Flask-CORS imported successfully")
except ImportError:
    logger.warning("Flask-CORS not available, continuing without CORS")
    CORS = None

# Create Flask app
logger.info("Creating Flask application instance...")
app = Flask(__name__)

if CORS:
    CORS(app)
    logger.info("CORS enabled")


# Simple route
@app.route('/')
def home():
    logger.info("Home route accessed")
    return jsonify({"status": "ok", "message": "Flask is running"})


@app.route('/health')
def health():
    return jsonify({"status": "healthy"})


def main():
    """Main entry point"""
    port = 5000
    host = '0.0.0.0'

    logger.info(f"Attempting to start Flask on {host}:{port}")

    # Check if port is available
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('', port))
        sock.close()
        logger.info(f"Port {port} is available")
    except OSError as e:
        logger.error(f"Port {port} is already in use: {e}")
        logger.error("Try: sudo lsof -i :5000  to see what's using it")
        logger.error("Or: sudo kill -9 $(sudo lsof -t -i:5000)  to kill it")
        return False

    # Try to start Flask
    try:
        logger.info("Starting Flask app.run()...")
        logger.info("If this hangs, Flask is likely starting but something else is wrong")
        logger.info("You should see: * Running on http://0.0.0.0:5000")

        # Start Flask with minimal options
        app.run(
            host=host,
            port=port,
            debug=True,
            use_reloader=False  # Disable reloader to avoid double startup
        )

    except Exception as e:
        logger.error(f"Failed to start Flask: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == '__main__':
    logger.info("Script started as main")
    success = main()
    if not success:
        logger.error("Flask failed to start")
        sys.exit(1)