#!/usr/bin/env python3
"""
Minimal SocketIO test server to verify the fix works
Run this to test SocketIO before applying to main application
"""

from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit, request as socketio_request
import subprocess
import threading
import time

app = Flask(__name__)
app.secret_key = 'test-secret-key'

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", allow_unsafe_werkzeug=True)

# Simple HTML test page
TEST_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>SocketIO Test</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.4.1/socket.io.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        #output { background: #000; color: #0f0; padding: 10px; height: 400px; overflow-y: auto; font-family: monospace; }
        button { padding: 10px 20px; margin: 5px; font-size: 16px; }
        .status { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .connected { background: #d4edda; color: #155724; }
        .disconnected { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>SocketIO Connection Test</h1>
    <div id="status" class="status disconnected">Connecting...</div>

    <button onclick="testCommand()">Test YouTube Command</button>
    <button onclick="testSimpleCommand()">Test Simple Command</button>
    <button onclick="clearOutput()">Clear Output</button>

    <div id="output"></div>

    <script>
        const socket = io();
        const statusDiv = document.getElementById('status');
        const outputDiv = document.getElementById('output');

        function addOutput(text, color = '#0f0') {
            const div = document.createElement('div');
            div.style.color = color;
            div.textContent = new Date().toLocaleTimeString() + ' - ' + text;
            outputDiv.appendChild(div);
            outputDiv.scrollTop = outputDiv.scrollHeight;
        }

        socket.on('connect', function() {
            console.log('Connected to server');
            statusDiv.innerHTML = 'Connected ✅';
            statusDiv.className = 'status connected';
            addOutput('SocketIO connected successfully', '#0f0');
        });

        socket.on('disconnect', function() {
            console.log('Disconnected from server');
            statusDiv.innerHTML = 'Disconnected ❌';
            statusDiv.className = 'status disconnected';
            addOutput('SocketIO disconnected', '#f00');
        });

        socket.on('connect_error', function(error) {
            console.error('Connection error:', error);
            statusDiv.innerHTML = 'Connection Error ❌';
            statusDiv.className = 'status disconnected';
            addOutput('Connection error: ' + error, '#f00');
        });

        socket.on('command_output', function(data) {
            console.log('Command output:', data);
            addOutput(data, '#0f0');
        });

        socket.on('command_completed', function(data) {
            console.log('Command completed:', data);
            addOutput('✅ Command completed: ' + JSON.stringify(data), '#ff0');
        });

        socket.on('command_error', function(data) {
            console.log('Command error:', data);
            addOutput('❌ Command error: ' + data, '#f00');
        });

        function testCommand() {
            addOutput('Sending YouTube command...', '#ff0');
            socket.emit('execute_command', 'python3 cli.py --media youtube --params download');
        }

        function testSimpleCommand() {
            addOutput('Sending simple command...', '#ff0');
            socket.emit('execute_command', 'python3 cli.py --version');
        }

        function clearOutput() {
            outputDiv.innerHTML = '';
        }

        // Test connection on load
        addOutput('Page loaded, testing connection...', '#0ff');
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(TEST_PAGE)


@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {socketio_request.sid}")
    emit('command_output', 'Server: Connection established')


@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {socketio_request.sid}")


@socketio.on('execute_command')
def handle_command(command):
    print(f"Received command: {command}")

    def run_command():
        try:
            emit('command_output', f'$ {command}')

            # Simple command execution
            process = subprocess.Popen(
                command.split(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Read output line by line
            for line in iter(process.stdout.readline, ''):
                if line:
                    line = line.rstrip()
                    print(f"Output: {line}")
                    socketio.emit('command_output', line)

            process.wait()

            if process.returncode == 0:
                socketio.emit('command_completed', {'data': 'Command completed successfully'})
            else:
                socketio.emit('command_error', f'Command exited with code {process.returncode}')

        except Exception as e:
            print(f"Error executing command: {e}")
            socketio.emit('command_error', str(e))

    # Run command in background thread
    thread = threading.Thread(target=run_command)
    thread.daemon = True
    thread.start()


if __name__ == '__main__':
    print("=" * 50)
    print("Starting SocketIO Test Server")
    print("=" * 50)
    print("Open your browser to: http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("=" * 50)

    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=5000,
            debug=True,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print("\nStopping server...")
    except Exception as e:
        print(f"Error: {e}")
        print("Try running with: python3 minimal_socketio_test.py")