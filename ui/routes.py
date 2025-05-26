from __main__ import app
from datetime import time

from flask import request, render_template, session, send_from_directory, jsonify, url_for, redirect
from flask_socketio import SocketIO, emit
import json
from clases.log import log as l
import re
from clases.worker import worker as w
from ui.ui import Ui
from ui.auth import auth_manager, requires_auth, requires_admin
import bcrypt
import ipaddress

_ui = Ui()
socketio = SocketIO(app)


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
            # Format: ["--media", "youtube", "--params", "direct"] or ["--media", "youtube", "--param", "direct"]
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
                # Parameter not found in expected format
                return jsonify({
                    'success': False,
                    'params': 'direct',  # Default parameter
                    'message': f'Parameter not found in cron config for {plugin_name}',
                    'full_command': do_array
                })
        else:
            # No cron found or missing parameters, return default
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
        auth_manager.log_security_event('invalid_login_attempt', 'Empty username or password', ip_address)
        return jsonify({
            'success': False,
            'message': 'Username and password are required'
        }), 400

    # Check if IP is whitelisted
    is_whitelisted = auth_manager.is_ip_whitelisted(ip_address)

    # Check if IP is locked (whitelisted IPs cannot be locked)
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

    # Check rate limiting (whitelisted IPs skip this)
    attempt_count = auth_manager.check_rate_limit(username, ip_address)
    if not is_whitelisted and attempt_count >= auth_manager.max_attempts:
        return jsonify({
            'success': False,
            'message': 'Too many failed attempts. IP address locked.',
            'locked': True
        }), 429

    # Check CAPTCHA if required (whitelisted IPs may skip this based on config)
    need_captcha = (not is_whitelisted and
                    attempt_count >= auth_manager.captcha_threshold and
                    auth_manager.config.get('auth_enable_captcha', True))

    if need_captcha:
        expected_answer = session.get('captcha_answer')
        if not captcha_answer or int(captcha_answer) != expected_answer:
            return jsonify({
                'success': False,
                'message': 'CAPTCHA verification failed!',
                'show_captcha': True,
                'attempts_remaining': max(0, auth_manager.max_attempts - attempt_count) if not is_whitelisted else None,
                'whitelisted': is_whitelisted
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

        # Log with whitelist status
        whitelist_note = " (whitelisted IP)" if is_whitelisted else ""
        auth_manager.log_security_event('successful_login',
                                        f'User {username} ({role}) logged in successfully{whitelist_note}',
                                        ip_address, username)

        # Redirect to original URL or dashboard
        next_url = session.pop('next_url', url_for('index'))
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'redirect_url': next_url,
            'role': role,
            'whitelisted': is_whitelisted
        })
    else:
        # Failed login
        auth_manager.record_failed_attempt(username, ip_address)

        # Log with whitelist status
        whitelist_note = " (whitelisted IP - no penalties applied)" if is_whitelisted else ""
        auth_manager.log_security_event('failed_login',
                                        f'Failed login attempt for user: {username}{whitelist_note}',
                                        ip_address, username)

        # Calculate remaining attempts (whitelisted IPs have unlimited attempts)
        if is_whitelisted:
            remaining_attempts = None  # Unlimited for whitelisted IPs
            message = f'Invalid credentials. (Whitelisted IP - unlimited attempts)'
        else:
            remaining_attempts = max(0, auth_manager.max_attempts - auth_manager.check_rate_limit(username, ip_address))
            message = f'Invalid credentials. {remaining_attempts} attempts remaining.'

        need_captcha = (not is_whitelisted and
                        auth_manager.check_rate_limit(username, ip_address) >= auth_manager.captcha_threshold and
                        auth_manager.config.get('auth_enable_captcha', True))

        return jsonify({
            'success': False,
            'message': message,
            'attempts_remaining': remaining_attempts,
            'show_captcha': need_captcha,
            'whitelisted': is_whitelisted
        }), 401


# =============================================================================
# ADD NEW API ENDPOINT FOR WHITELIST MANAGEMENT
# =============================================================================

@app.route('/api/security/whitelist', methods=['GET'])
@requires_auth
@requires_admin
def get_whitelist():
    """Get current IP whitelist configuration (admin only)"""
    return jsonify({
        'enabled': auth_manager.enable_ip_whitelist,
        'whitelist': auth_manager.ip_whitelist_raw,
        'parsed_count': len(auth_manager.ip_whitelist),
        'current_ip': request.remote_addr,
        'current_ip_whitelisted': auth_manager.is_ip_whitelisted(request.remote_addr)
    })


@app.route('/api/security/whitelist/test', methods=['POST'])
@requires_auth
@requires_admin
def test_whitelist():
    """Test if an IP would be whitelisted (admin only)"""
    data = request.get_json()
    test_ip = data.get('ip', '').strip()

    if not test_ip:
        return jsonify({'error': 'IP address required'}), 400

    try:
        is_whitelisted = auth_manager.is_ip_whitelisted(test_ip)
        return jsonify({
            'ip': test_ip,
            'whitelisted': is_whitelisted,
            'whitelist_enabled': auth_manager.enable_ip_whitelist
        })
    except Exception as e:
        return jsonify({'error': f'Invalid IP address: {str(e)}'}), 400


@app.route('/api/security/whitelist/add', methods=['POST'])
@requires_auth
@requires_admin
def add_to_whitelist():
    """Add IP to whitelist (admin only)"""
    data = request.get_json()
    ip_entry = data.get('ip', '').strip()

    if not ip_entry:
        return jsonify({'error': 'IP address or CIDR block required'}), 400

    try:
        # Validate the IP entry
        if '/' in ip_entry:
            ipaddress.ip_network(ip_entry, strict=False)
        else:
            ipaddress.ip_address(ip_entry)

        # Get current config
        config = auth_manager.config
        if 'security_settings' not in config:
            config['security_settings'] = {}
        if 'rate_limiting' not in config['security_settings']:
            config['security_settings']['rate_limiting'] = {}

        # Add to whitelist
        current_whitelist = config['security_settings']['rate_limiting'].get('ip_whitelist', [])
        if ip_entry not in current_whitelist:
            current_whitelist.append(ip_entry)
            config['security_settings']['rate_limiting']['ip_whitelist'] = current_whitelist

            # Save and reload
            if auth_manager.save_config(config):
                auth_manager.config = config
                auth_manager.ip_whitelist_raw = current_whitelist
                auth_manager.ip_whitelist = auth_manager.parse_ip_whitelist(current_whitelist)

                auth_manager.log_security_event('whitelist_updated',
                                                f'IP {ip_entry} added to whitelist by admin',
                                                request.remote_addr, session.get('username'))

                return jsonify({
                    'success': True,
                    'message': f'IP {ip_entry} added to whitelist',
                    'whitelist': current_whitelist
                })
            else:
                return jsonify({'error': 'Failed to save configuration'}), 500
        else:
            return jsonify({'error': 'IP already in whitelist'}), 400

    except ValueError as e:
        return jsonify({'error': f'Invalid IP address or CIDR block: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to add IP: {str(e)}'}), 500


@app.route('/api/security/whitelist/remove', methods=['POST'])
@requires_auth
@requires_admin
def remove_from_whitelist():
    """Remove IP from whitelist (admin only)"""
    data = request.get_json()
    ip_entry = data.get('ip', '').strip()

    if not ip_entry:
        return jsonify({'error': 'IP address required'}), 400

    try:
        # Get current config
        config = auth_manager.config
        current_whitelist = config.get('security_settings', {}).get('rate_limiting', {}).get('ip_whitelist', [])

        if ip_entry in current_whitelist:
            current_whitelist.remove(ip_entry)
            config['security_settings']['rate_limiting']['ip_whitelist'] = current_whitelist

            # Save and reload
            if auth_manager.save_config(config):
                auth_manager.config = config
                auth_manager.ip_whitelist_raw = current_whitelist
                auth_manager.ip_whitelist = auth_manager.parse_ip_whitelist(current_whitelist)

                auth_manager.log_security_event('whitelist_updated',
                                                f'IP {ip_entry} removed from whitelist by admin',
                                                request.remote_addr, session.get('username'))

                return jsonify({
                    'success': True,
                    'message': f'IP {ip_entry} removed from whitelist',
                    'whitelist': current_whitelist
                })
            else:
                return jsonify({'error': 'Failed to save configuration'}), 500
        else:
            return jsonify({'error': 'IP not found in whitelist'}), 404

    except Exception as e:
        return jsonify({'error': f'Failed to remove IP: {str(e)}'}), 500


@app.route('/api/security/whitelist/toggle', methods=['POST'])
@requires_auth
@requires_admin
def toggle_whitelist():
    """Enable/disable IP whitelist (admin only)"""
    data = request.get_json()
    enable = data.get('enable', False)

    try:
        # Get current config
        config = auth_manager.config
        if 'security_settings' not in config:
            config['security_settings'] = {}
        if 'rate_limiting' not in config['security_settings']:
            config['security_settings']['rate_limiting'] = {}

        config['security_settings']['rate_limiting']['enable_ip_whitelist'] = bool(enable)

        # Save and reload
        if auth_manager.save_config(config):
            auth_manager.config = config
            auth_manager.enable_ip_whitelist = bool(enable)

            status = "enabled" if enable else "disabled"
            auth_manager.log_security_event('whitelist_toggled',
                                            f'IP whitelist {status} by admin',
                                            request.remote_addr, session.get('username'))

            return jsonify({
                'success': True,
                'message': f'IP whitelist {status}',
                'enabled': bool(enable),
                'whitelist_count': len(auth_manager.ip_whitelist_raw)
            })
        else:
            return jsonify({'error': 'Failed to save configuration'}), 500

    except Exception as e:
        return jsonify({'error': f'Failed to toggle whitelist: {str(e)}'}), 500



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
    """Security monitoring endpoint with whitelist info (admin only)"""
    stats = auth_manager.get_security_stats()

    # Add current request IP info
    current_ip = request.remote_addr
    stats['current_session'] = {
        'ip': current_ip,
        'whitelisted': auth_manager.is_ip_whitelisted(current_ip),
        'user': session.get('username'),
        'role': session.get('role')
    }

    return jsonify(stats)

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
                    # FIXED: Changed from --param to --params for consistency
                    crons[_x]['do'].append('--params')  # Changed this line
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


# Store to prevent duplicate command executions
_command_executions = {}


@socketio.on('execute_command')
def handle_command(command):
    """Handle command execution with duplicate prevention"""
    # Add authentication check for socket.io commands
    if 'authenticated' not in session or not session['authenticated']:
        emit('command_error', 'Authentication required')
        return

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

    # Execute the command
    _ui.handle_command(command)

@app.route('/test-socketio')
def test_socketio():
    return '''
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.4.1/socket.io.js"></script>
    <script>
    const socket = io();
    socket.on('connect', () => console.log('Connected!'));
    socket.emit('execute_command', 'python3 cli.py --media youtube --params download');
    </script>
    <h1>Check browser console</h1>
    '''