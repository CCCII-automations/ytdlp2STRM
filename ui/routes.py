from __main__ import app
from datetime import time

from flask import request, render_template, session, send_from_directory, jsonify, url_for, redirect
from flask_socketio import SocketIO, emit
import json
import logging
import re
from clases.worker import worker as w
from ui.ui import Ui
from ui.auth import auth_manager, requires_auth, requires_admin
import bcrypt

_ui = Ui()
socketio = SocketIO(app)
logging.getLogger('werkzeug').setLevel(logging.WARNING)


# =============================================================================
# UPDATE YOUR EXISTING ROUTES BY ADDING @requires_auth DECORATOR
# =============================================================================

# Update your existing index route
@app.route('/')
@requires_auth  # Add this line
def index():
    crons = _ui.crons
    return render_template(
        'index.html',
        plugins=_ui.plugins,
        crons=crons
    )


# Update your existing API routes
@app.route('/api/update-plugins', methods=['POST'])
@requires_auth  # Add this line
def api_update_plugins():
    # Your existing code remains the same
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
@requires_auth  # Add this line
def api_status():
    # Your existing code remains the same
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
@requires_auth  # Add this line
def api_run_plugin(plugin_name):
    # Your existing code remains the same
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


# =============================================================================
# UPDATE YOUR GENERAL SETTINGS ROUTE TO HANDLE AUTH CONFIG
# =============================================================================

@app.route('/general', methods=['GET', 'POST'])
@requires_auth  # Add this line
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
        if auth_manager.update_auth_config(config_data):
            result = True
        else:
            # Fallback to old method for backward compatibility
            _ui.general_settings = config_data
            result = True

    # Get current configuration (including auth settings)
    config_data = auth_manager.config if hasattr(auth_manager, 'config') else _ui.general_settings
    if config_data:
        result = result or (request.method == 'GET')

    return render_template(
        'general_settings.html',
        config_data=config_data,
        result=result,
        request=request.method
    )


# =============================================================================
# ADD NEW AUTHENTICATION ROUTES
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Authentication endpoint"""
    if request.method == 'GET':
        return render_template('login.html')

    # Handle login POST request
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    captcha_answer = request.form.get('captcha_answer', '')
    ip_address = request.remote_addr

    # Basic input validation
    if not username or not password:
        auth_manager.log_security_event('invalid_login_attempt', 'Empty username or password', ip_address)
        return jsonify({
            'success': False,
            'message': 'Username and password are required'
        }), 400

    # Check if IP is locked
    is_locked, unlock_time = auth_manager.is_ip_locked(ip_address)
    if is_locked:
        remaining_time = int(unlock_time - time.time())
        auth_manager.log_security_event('locked_ip_attempt',
                                        f'Login attempt from locked IP: {ip_address}',
                                        ip_address, username)
        return jsonify({
            'success': False,
            'message': f'IP address locked. Try again in {remaining_time} seconds.',
            'locked': True,
            'unlock_time': remaining_time
        }), 429

    # Check rate limiting
    attempt_count = auth_manager.check_rate_limit(username, ip_address)
    if attempt_count >= auth_manager.max_attempts:
        return jsonify({
            'success': False,
            'message': 'Too many failed attempts. IP address locked.',
            'locked': True
        }), 429

    # Check CAPTCHA if required
    need_captcha = attempt_count >= auth_manager.captcha_threshold
    if need_captcha and auth_manager.config.get('auth_enable_captcha', True):
        expected_answer = session.get('captcha_answer')
        if not captcha_answer or int(captcha_answer) != expected_answer:
            return jsonify({
                'success': False,
                'message': 'CAPTCHA verification failed!',
                'show_captcha': True,
                'attempts_remaining': max(0, auth_manager.max_attempts - attempt_count)
            }), 400

    # Verify credentials
    is_valid, role = auth_manager.verify_credentials(username, password)
    if is_valid:
        # Successful login
        session['authenticated'] = True
        session['username'] = username
        session['role'] = role
        session.permanent = True

        # Clear failed attempts
        auth_manager.clear_failed_attempts(username, ip_address)

        auth_manager.log_security_event('successful_login',
                                        f'User {username} ({role}) logged in successfully',
                                        ip_address, username)

        # Redirect to original URL or dashboard
        next_url = session.pop('next_url', url_for('index'))
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'redirect_url': next_url,
            'role': role
        })
    else:
        # Failed login
        auth_manager.record_failed_attempt(username, ip_address)
        auth_manager.log_security_event('failed_login',
                                        f'Failed login attempt for user: {username}',
                                        ip_address, username)

        remaining_attempts = max(0, auth_manager.max_attempts - auth_manager.check_rate_limit(username, ip_address))
        need_captcha = auth_manager.check_rate_limit(username, ip_address) >= auth_manager.captcha_threshold

        return jsonify({
            'success': False,
            'message': f'Invalid credentials. {remaining_attempts} attempts remaining.',
            'attempts_remaining': remaining_attempts,
            'show_captcha': need_captcha and auth_manager.config.get('auth_enable_captcha', True)
        }), 401


@app.route('/api/captcha')
def generate_captcha():
    """Generate CAPTCHA challenge"""
    if not auth_manager.config.get('auth_enable_captcha', True):
        return jsonify({'error': 'CAPTCHA disabled'}), 404

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
    auth_manager.log_security_event('logout', f'User {username} logged out', request.remote_addr, username)

    session.clear()
    return redirect(url_for('login'))


@app.route('/api/security/status')
@requires_auth
@requires_admin
def security_status():
    """Security monitoring endpoint (admin only)"""
    return jsonify(auth_manager.get_security_stats())


@app.route('/api/security/unlock-ip', methods=['POST'])
@requires_auth
@requires_admin
def unlock_ip():
    """Unlock a specific IP address (admin only)"""
    data = request.get_json()
    ip_address = data.get('ip')

    if not ip_address:
        return jsonify({'error': 'IP address required'}), 400

    # Remove the IP from locked list
    locked_ips = auth_manager.load_locked_ips()
    original_count = len(locked_ips)
    locked_ips = [lock for lock in locked_ips if lock.get('ip') != ip_address]

    if len(locked_ips) < original_count:
        auth_manager.save_locked_ips(locked_ips)
        auth_manager.log_security_event('ip_unlocked', f'IP {ip_address} manually unlocked by admin',
                                        request.remote_addr, session.get('username'))
        return jsonify({'success': True, 'message': f'IP {ip_address} unlocked'})
    else:
        return jsonify({'error': 'IP address not found in locked list'}), 404


@app.route('/api/users/add', methods=['POST'])
@requires_auth
@requires_admin
def add_user():
    """Add a new user (admin only)"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'user')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    if role not in ['user', 'admin']:
        return jsonify({'error': 'Invalid role'}), 400

    # Check if user already exists
    admins = auth_manager.config.get('admins', {})
    users = auth_manager.config.get('users', {})

    if username in admins or username in users:
        return jsonify({'error': 'User already exists'}), 400

    if auth_manager.add_user(username, password, role):
        auth_manager.log_security_event('user_added', f'User {username} ({role}) added by admin',
                                        request.remote_addr, session.get('username'))
        return jsonify({'success': True, 'message': f'User {username} added successfully'})
    else:
        return jsonify({'error': 'Failed to add user'}), 500


@app.route('/api/users/remove', methods=['POST'])
@requires_auth
@requires_admin
def remove_user():
    """Remove a user (admin only)"""
    data = request.get_json()
    username = data.get('username', '').strip()

    if not username:
        return jsonify({'error': 'Username required'}), 400

    if username == 'admin':
        return jsonify({'error': 'Cannot remove default admin user'}), 400

    if auth_manager.remove_user(username):
        auth_manager.log_security_event('user_removed', f'User {username} removed by admin',
                                        request.remote_addr, session.get('username'))
        return jsonify({'success': True, 'message': f'User {username} removed successfully'})
    else:
        return jsonify({'error': 'User not found or failed to remove'}), 404


@app.route('/api/users/change-password', methods=['POST'])
@requires_auth
@requires_admin
def change_user_password():
    """Change user password (admin only)"""
    data = request.get_json()
    username = data.get('username', '').strip()
    new_password = data.get('password', '').strip()

    if not username or not new_password:
        return jsonify({'error': 'Username and password required'}), 400

    # Find user in config
    config = auth_manager.config
    user_found = False

    if username in config.get('admins', {}):
        config['admins'][username]['password'] = auth_manager.hash_password(new_password)
        user_found = True
    elif username in config.get('users', {}):
        config['users'][username]['password'] = auth_manager.hash_password(new_password)
        user_found = True

    if user_found and auth_manager.save_config(config):
        auth_manager.log_security_event('password_changed', f'Password changed for user {username} by admin',
                                        request.remote_addr, session.get('username'))
        return jsonify({'success': True, 'message': f'Password changed for {username}'})
    else:
        return jsonify({'error': 'User not found or failed to update password'}), 404


# =============================================================================
# UPDATE ALL YOUR OTHER EXISTING ROUTES WITH @requires_auth
# =============================================================================

@app.route('/plugins', methods=['GET', 'POST'])
@requires_auth  # Add this line
def plugin_py_settings():
    # Your existing code remains unchanged
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
@requires_auth  # Add this line
def crons_settings():
    # Your existing code remains unchanged
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
                    crons[_x]['do'].append('--param')
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
@requires_auth  # Add this line
def plugin(plugin):
    # Your existing code remains unchanged
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
@requires_auth  # Add this line
def plugin_channels(plugin):
    # Your existing code remains unchanged
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
@requires_auth  # Add this line
def view_log():
    # Your existing code remains unchanged
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


# Your existing socketio handler
@socketio.on('execute_command')
def handle_command(command):
    # Add authentication check for socket.io commands
    if 'authenticated' not in session or not session['authenticated']:
        emit('command_error', 'Authentication required')
        return

    _ui.handle_command(command)