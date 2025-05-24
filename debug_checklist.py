#!/usr/bin/env python3
"""
Flask Service Debugging Script
Run this to diagnose why Flask isn't starting on port 5000
"""

import socket
import subprocess
import sys
import os
import psutil
import time
from datetime import datetime


def print_section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def check_python_environment():
    """Check Python environment details"""
    print_section("PYTHON ENVIRONMENT")
    print(f"Python Version: {sys.version}")
    print(f"Python Executable: {sys.executable}")
    print(f"Current Working Directory: {os.getcwd()}")
    print(f"Process ID: {os.getpid()}")

    # Check installed packages
    try:
        import flask
        print(f"Flask Version: {flask.__version__}")
    except ImportError:
        print("ERROR: Flask is not installed!")

    try:
        import flask_cors
        print("Flask-CORS: Installed")
    except ImportError:
        print("WARNING: Flask-CORS is not installed")


def check_port_status(port=5000):
    """Check if port is in use and by what process"""
    print_section(f"PORT {port} STATUS")

    # Method 1: Try to bind to the port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('', port))
        sock.close()
        print(f"✓ Port {port} is AVAILABLE")
        return True
    except OSError as e:
        print(f"✗ Port {port} is IN USE: {e}")

        # Method 2: Find what's using the port
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    for conn in proc.connections('inet'):
                        if conn.laddr.port == port:
                            print(f"  Process using port: {proc.info['name']} (PID: {proc.info['pid']})")
                            print(f"  Full command: {' '.join(proc.cmdline())}")
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    pass
        except:
            # Fallback to system commands
            if sys.platform == "win32":
                cmd = f"netstat -ano | findstr :{port}"
            else:
                cmd = f"lsof -i :{port} 2>/dev/null || netstat -tlnp 2>/dev/null | grep :{port}"

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.stdout:
                print(f"  System info: {result.stdout.strip()}")

        return False


def check_firewall():
    """Check firewall status"""
    print_section("FIREWALL STATUS")

    if sys.platform == "linux":
        # Check iptables
        cmd = "sudo iptables -L -n | grep 5000 2>/dev/null"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("iptables rules for port 5000:")
            print(result.stdout or "  No specific rules found")

        # Check ufw
        cmd = "sudo ufw status 2>/dev/null"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("\nUFW Status:")
            print(result.stdout)

    elif sys.platform == "darwin":
        cmd = "sudo pfctl -s rules 2>/dev/null | grep 5000"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print("macOS Firewall rules for port 5000:")
        print(result.stdout or "  No specific rules found")

    elif sys.platform == "win32":
        cmd = "netsh advfirewall firewall show rule name=all | findstr 5000"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print("Windows Firewall rules for port 5000:")
        print(result.stdout or "  No specific rules found")


def test_minimal_flask():
    """Test a minimal Flask app"""
    print_section("TESTING MINIMAL FLASK APP")

    test_code = '''
import flask
app = flask.Flask(__name__)

@app.route('/')
def home():
    return 'Test OK'

print("Attempting to start test Flask app...")
try:
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)
except Exception as e:
    print(f"Test failed: {e}")
'''

    print("Creating minimal test app on port 5001...")
    with open('test_flask.py', 'w') as f:
        f.write(test_code)

    # Run in subprocess with timeout
    try:
        proc = subprocess.Popen([sys.executable, 'test_flask.py'],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True)

        # Give it 3 seconds to start
        time.sleep(3)

        # Check if it's running
        if proc.poll() is None:
            print("✓ Test Flask app started successfully!")

            # Try to connect
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect(('127.0.0.1', 5001))
                sock.close()
                print("✓ Successfully connected to test app")
            except:
                print("✗ Could not connect to test app")

            proc.terminate()
        else:
            stdout, stderr = proc.communicate()
            print("✗ Test Flask app failed to start")
            print(f"STDOUT: {stdout}")
            print(f"STDERR: {stderr}")

    except Exception as e:
        print(f"Test error: {e}")
    finally:
        if os.path.exists('test_flask.py'):
            os.remove('test_flask.py')


def check_permissions():
    """Check file and socket permissions"""
    print_section("PERMISSIONS CHECK")

    # Check current user
    try:
        import pwd
        print(f"Current user: {pwd.getpwuid(os.getuid()).pw_name}")
    except:
        print(f"Current user ID: {os.getuid() if hasattr(os, 'getuid') else 'N/A'}")

    # Check main.py permissions
    if os.path.exists('main.py'):
        stat = os.stat('main.py')
        print(f"main.py permissions: {oct(stat.st_mode)[-3:]}")

    # Check socket permissions
    socket_path = '/tmp/app_socket'
    if os.path.exists(socket_path):
        stat = os.stat(socket_path)
        print(f"Socket permissions: {oct(stat.st_mode)[-3:]}")


def suggest_fixes():
    """Suggest potential fixes"""
    print_section("SUGGESTED FIXES")

    print("1. Kill process using port 5000:")
    print("   Linux/Mac: sudo kill -9 $(sudo lsof -t -i:5000)")
    print("   Windows: netstat -ano | findstr :5000")
    print("            taskkill /PID <PID> /F")

    print("\n2. Try different port:")
    print("   Modify main.py: app.run(port=5001)")

    print("\n3. Check Flask installation:")
    print("   pip install --upgrade flask flask-cors")

    print("\n4. Run with explicit Python:")
    print("   python3 main.py")

    print("\n5. Check for syntax errors:")
    print("   python3 -m py_compile main.py")

    print("\n6. Enable verbose Flask logging:")
    print("   export FLASK_ENV=development")
    print("   export FLASK_DEBUG=1")


# Run all checks
if __name__ == "__main__":
    print(f"Flask Service Debugging - {datetime.now()}")

    check_python_environment()
    check_port_status(5000)
    check_permissions()
    check_firewall()
    test_minimal_flask()
    suggest_fixes()

    print("\n" + "=" * 60)
    print("Debugging complete. Check the output above for issues.")
    print("=" * 60)