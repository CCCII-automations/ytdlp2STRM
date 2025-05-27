import threading
from __main__ import app
import time

from flask import request, render_template, session, send_from_directory, jsonify, url_for, redirect
from flask_socketio import emit  # Only import emit, not SocketIO
import json
from clases.log import log as l
import re
from clases.worker import worker as w
from ui.ui import Ui
from ui.auth import auth_manager, requires_auth, requires_admin
import bcrypt
import ipaddress

_ui = Ui()


# REMOVE the socketio = SocketIO(app) line completely
# We'll get the socketio instance from main.py instead

# All your existing routes stay exactly the same
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


@app.route('/api/run-plugin/<plugin_name>', methods=['POST'])
def api_run_plugin(plugin_name):
    try:
        # Validate plugin exists and is enabled
        plugins = _ui.plugins
        plugin = next((p for p in plugins if p['name'] == plugin_name), None)

        if not plugin:
            return jsonify({'success': False, 'error': 'Plugin not found'}), 404

        if not plugin.get('enabled', False):
            return jsonify({'success': False, 'error': 'Plugin is disabled'}), 400

        # Execute the plugin via command
        command = f"python3 cli.py --media {plugin_name}"

        return jsonify({
            'success': True,
            'message': f'Plugin {plugin_name} execution started',
            'command': command
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get-cron-params/<plugin_name>', methods=['GET'])
def get_cron_params(plugin_name):
    """Get cron parameters for a specific plugin"""
    try:
        crons = _ui.crons

        # Find cron configuration for this plugin
        plugin_cron = None
        for cron in crons:
            if len(cron.get('do', [])) >= 2 and cron['do'][1] == plugin_name:
                plugin_cron = cron
                break

        if plugin_cron and len(plugin_cron.get('do', [])) >= 4:
            # Extract the parameter from the cron configuration
            param_index = -1
            do_array = plugin_cron['do']

            # Find the parameter value (after --params or --param)
            for i, item in enumerate(do_array):
                if item in ['--params', '--param']:
                    if i + 1 < len(do_array):
                        param_index = i + 1
                        break

            if param_index > 0:
                params = do_array[param_index]  # Get the parameter value

                return jsonify({
                    'success': True,
                    'params': params,
                    'cron_config': {
                        'every': plugin_cron.get('every'),
                        'qty': plugin_cron.get('qty'),
                        'at': plugin_cron.get('at'),
                        'timezone': plugin_cron.get('timezone')
                    },
                    'full_command': do_array
                })
            else:
                return jsonify({
                    'success': False,
                    'params': 'direct',  # Default parameter
                    'message': f'Parameter not found in cron config for {plugin_name}',
                    'full_command': do_array
                })
        else:
            return jsonify({
                'success': False,
                'params': 'direct',  # Default parameter
                'message': f'No cron configuration found for {plugin_name}',
                'available_crons': [cron.get('do', []) for cron in crons]
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'params': 'direct'  # Fallback parameter
        }), 500


@app.route('/general', methods=['GET', 'POST'])
@requires_auth
def general_settings():
    result = False
    if request.method == 'POST':
        # Get form values including authentication settings
        config_data = {}
        for key, value in request.form.items():
            config_data[key] = value

        # Handle checkbox values (convert to proper boolean)
        checkbox_fields = ['ytdlp2strm_keep_old_strm', 'auth_enable_captcha', 'auth_log_events']
        for field in checkbox_fields:
            if field in config_data:
                config_data[field] = config_data[field] == 'True'

        # Convert numeric fields
        numeric_fields = [
            'ytdlp2strm_port', 'ytdlp2strm_temp_file_duration',
            'auth_max_attempts', 'auth_lockout_time', 'auth_captcha_threshold',
            'auth_base_delay', 'auth_session_timeout'
        ]
        for field in numeric_fields:
            if field in config_data:
                try:
                    config_data[field] = int(config_data[field])
                except ValueError:
                    pass

        # Update auth manager configuration
        if hasattr(auth_manager, 'update_auth_config') and auth_manager.update_auth_config(config_data):
            result = True
        else:
            # Fallback to old method for backward compatibility
            _ui.general_settings = config_data
            result = True

    # Get current configuration (including auth settings)
    config_data = getattr(auth_manager, 'config', _ui.general_settings)
    if config_data:
        result = result or (request.method == 'GET')

    return render_template(
        'general_settings.html',
        config_data=config_data,
        result=result,
        request=request.method
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Authentication endpoint with IP whitelist support"""
    if request.method == 'GET':
        return render_template('login.html')

    # Handle login POST request
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    captcha_answer = request.form.get('captcha_answer', '')
    ip_address = request.remote_addr

    # Basic input validation
    if not username or not password:
        if hasattr(auth_manager, 'log_security_event'):
            auth_manager.log_security_event('invalid_login_attempt', 'Empty username or password', ip_address)
        return jsonify({
            'success': False,
            'message': 'Username and password are required'
        }), 400

    # Simple auth check (enhance as needed)
    if hasattr(auth_manager, 'verify_credentials'):
        is_valid, role = auth_manager.verify_credentials(username, password)
        if is_valid:
            session['authenticated'] = True
            session['username'] = username
            session['role'] = role
            session.permanent = True
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'redirect_url': url_for('index')
            })

    return jsonify({
        'success': False,
        'message': 'Invalid credentials'
    }), 401


@app.route('/api/captcha')
def generate_captcha():
    """Generate CAPTCHA challenge"""
    import random
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    operators = ['+', '-', '*']
    operator = random.choice(operators)

    if operator == '+':
        answer = num1 + num2
    elif operator == '-':
        answer = num1 - num2
    else:  # *
        answer = num1 * num2

    session['captcha_answer'] = answer

    return jsonify({
        'question': f'{num1} {operator} {num2} = ?'
    })


@app.route('/logout')
def logout():
    """Logout endpoint"""
    username = session.get('username', 'Unknown')
    if hasattr(auth_manager, 'log_security_event'):
        auth_manager.log_security_event('logout', f'User {username} logged out', request.remote_addr, username)
    session.clear()
    return redirect(url_for('login'))


@app.route('/plugins', methods=['GET', 'POST'])
@requires_auth
def plugin_py_settings():
    result = False
    if request.method == 'POST':
        plugin_code = request.form.getlist('plugin_field')
        _ui.plugins_py = '\n'.join(plugin_code)

    plugin_code = _ui.plugins_py.splitlines()

    if plugin_code:
        result = True

    return render_template(
        'plugin_py_settings.html',
        result=result,
        plugin_code=plugin_code,
        request=request.method
    )


@app.route('/crons', methods=['GET', 'POST'])
@requires_auth
def crons_settings():
    result = False
    if request.method == 'POST':
        headers = ('every', 'qty', 'at', 'timezone', 'plugin', 'param')
        values = (
            request.form.getlist('every[]'),
            request.form.getlist('qty[]'),
            request.form.getlist('at[]'),
            request.form.getlist('timezone[]'),
            request.form.getlist('plugin[]'),
            request.form.getlist('param[]'),
        )
        crons = [{} for i in range(len(values[0]))]
        for x, i in enumerate(values):
            for _x, _i in enumerate(i):
                if not headers[x] == 'plugin' and not headers[x] == 'param':
                    crons[_x][headers[x]] = _i
                elif headers[x] == 'plugin':
                    crons[_x]['do'] = ['--media', _i]
                elif headers[x] == 'param':
                    crons[_x]['do'].append('--params')
                    crons[_x]['do'].append(_i)

        _ui.crons = json.dumps(crons)

    crons = _ui.crons
    plugins = _ui.plugins
    if crons:
        result = True

    return render_template(
        'crons.html',
        result=result,
        crons=crons,
        plugins=plugins,
        request=request.method
    )


@app.route('/plugin/<plugin>', methods=['GET', 'POST'])
@requires_auth
def plugin(plugin):
    plugins = _ui.plugins
    selected_plugin = list(filter(lambda p: p['name'] == plugin, plugins))
    result = False
    if request.method == 'POST':
        config_data = {}
        config_data['config_file'] = '{}/{}/{}'.format(
            './plugins',
            selected_plugin[0]['name'],
            'config.json'
        )
        for key, value in request.form.items():
            config_data[key] = value

        _ui.plugins = config_data

        if config_data:
            result = True

        plugins = _ui.plugins
        selected_plugin = list(filter(lambda p: p['name'] == plugin, plugins))

    return render_template(
        'plugin_settings.html',
        plugin=selected_plugin[0],
        result=result,
        request=request.method
    )


@app.route('/plugin/<plugin>/channels', methods=['GET', 'POST'])
@requires_auth
def plugin_channels(plugin):
    result = False
    plugins = _ui.plugins

    selected_plugin = list(filter(lambda p: p['name'] == plugin, plugins))

    if request.method == 'POST':
        config_data = {}
        config_data['config_file'] = '{}/{}/{}'.format(
            './plugins',
            selected_plugin[0]['name'],
            'channel_list.json'
        )
        config_data['channels'] = request.form.getlist('channels')
        _ui.plugins = config_data

        if config_data['channels']:
            result = True

        plugins = _ui.plugins
        selected_plugin = list(filter(lambda p: p['name'] == plugin, plugins))

    return render_template(
        'plugin_channels.html',
        plugin=selected_plugin[0],
        result=result,
        request=request.method
    )


@app.route('/log')
@requires_auth
def view_log():
    log_file = 'logs/ytdlp2strm.log'
    try:
        log_content = []
        with open(log_file, 'r', encoding='utf-8') as file:
            for line in file:
                if line.startswith('['):
                    end_idx = line.find(']')
                    if end_idx != -1:
                        formatted_line = '[<span style="color:yellowgreen;">' + line[1:end_idx] + '</span>]' + line[
                                                                                                               end_idx + 1:]
                    else:
                        formatted_line = line
                else:
                    formatted_line = line
                log_content.append(formatted_line + '<br/>')
        return render_template('log.html', log_content=log_content)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


# Store to prevent duplicate command executions
_command_executions = {}


# This will be called by main.py after SocketIO is initialized
# This will be called by main.py after SocketIO is initialized
def register_socketio_events(socketio_instance):
    """Register SocketIO events with the main SocketIO instance"""

    # IMPORTANT: Pass the socketio instance to the UI class
    global _ui
    _ui = Ui(socketio_instance)  # Pass socketio to UI class

    @socketio_instance.on('connect')
    def handle_connect():
        """Handle client connection"""
        l.log("routes", f"Socket.IO client connected")
        socketio_instance.emit('command_output', '✓ Connected to server')

    @socketio_instance.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection"""
        l.log("routes", f"Socket.IO client disconnected")

    @socketio_instance.on('execute_command')
    def handle_command(command):
        """Handle command execution with duplicate prevention"""
        l.log("routes", f"Received Socket.IO command: {command}")

        # Prevent duplicate commands
        current_time = time.time()
        command_hash = hash(command)

        # Check if this exact command was executed very recently (within 2 seconds)
        if command_hash in _command_executions:
            last_execution = _command_executions[command_hash]
            if current_time - last_execution < 2.0:
                l.log("routes", f"Ignoring duplicate command execution: {command}")
                return

        # Record this execution
        _command_executions[command_hash] = current_time

        # Clean old entries (keep only last 10 commands)
        if len(_command_executions) > 10:
            oldest_hash = min(_command_executions.keys(),
                              key=lambda h: _command_executions[h])
            del _command_executions[oldest_hash]

        l.log("routes", f"Executing command: {command}")

        # Execute the command in a separate thread to prevent blocking
        def execute_in_thread():
            try:
                _ui.handle_command(command)
            except Exception as e:
                l.log("routes", f"Error executing command: {e}")
                socketio_instance.emit('command_error', f'Error executing command: {str(e)}')

        # Start execution in background thread
        thread = threading.Thread(target=execute_in_thread)
        thread.daemon = True
        thread.start()

    l.log("routes", "SocketIO events registered successfully")

# For backwards compatibility, add a test route
@app.route('/test-socketio')
def test_socketio():
    return '''
    <h1>SocketIO Test</h1>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.4.1/socket.io.js"></script>
    <script>
    const socket = io();
    socket.on('connect', () => {
        console.log('Connected!');
        document.body.innerHTML += '<p style="color: green;">✓ Connected to SocketIO</p>';
    });
    socket.on('disconnect', () => {
        console.log('Disconnected!');
        document.body.innerHTML += '<p style="color: red;">✗ Disconnected from SocketIO</p>';
    });
    socket.on('connect_error', (error) => {
        console.error('Connection error:', error);
        document.body.innerHTML += '<p style="color: red;">❌ Connection Error: ' + error + '</p>';
    });
    </script>
    <p>Check browser console and this page for connection status</p>
    '''