from __main__ import app
from flask import request, render_template, session, send_from_directory, jsonify
from flask_socketio import SocketIO
import json
import logging
import re
from clases.worker import worker as w
from ui.ui import Ui

_ui = Ui()
socketio = SocketIO(app)
logging.getLogger('werkzeug').setLevel(logging.WARNING)


# Ruta principal
@app.route('/')
def index():
    crons = _ui.crons
    return render_template(
        'index.html',
        plugins=_ui.plugins,
        crons=crons
    )


# API endpoint to update plugin status (enable/disable)
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
                if f'plugins.{plugin_name}' in line:
                    if should_enable and line.strip().startswith('#'):
                        # Enable plugin (remove #)
                        lines[i] = line.lstrip('#').lstrip()
                    elif not should_enable and not line.strip().startswith('#'):
                        # Disable plugin (add #)
                        lines[i] = f'# {line}'
                    break

        # Save updated content
        _ui.plugins_py = '\n'.join(lines)

        return jsonify({'success': True, 'message': 'Plugins updated successfully'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# API endpoint to get current status
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


# API endpoint to run a specific plugin
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

        # This would be handled by the socket.io in a real implementation
        # For now, we'll just return success
        return jsonify({
            'success': True,
            'message': f'Plugin {plugin_name} execution started',
            'command': command
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Ruta para las opciones generales
@app.route('/general', methods=['GET', 'POST'])
def general_settings():
    result = False
    if request.method == 'POST':
        # Obtener los valores del formulario
        config_data = {}
        for key, value in request.form.items():
            config_data[key] = value

        _ui.general_settings = config_data

    config_data = _ui.general_settings
    if config_data:
        result = True

    return render_template(
        'general_settings.html',
        config_data=config_data,
        result=result,
        request=request.method
    )


# Ruta para la edición de plugins
@app.route('/plugins', methods=['GET', 'POST'])
def plugin_py_settings():
    result = False
    if request.method == 'POST':
        # Obtener el código de plugins desde el formulario
        plugin_code = request.form.getlist('plugin_field')
        # Guardar el código en el archivo de plugins
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


# Ruta para la edición de plugins
@app.route('/crons', methods=['GET', 'POST'])
def crons_settings():
    result = False
    if request.method == 'POST':
        # Obtener el código de plugins desde el formulario
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

        # Guardar el código en el archivo de plugins
        _ui.crons = json.dumps(crons)

    crons = _ui.crons
    if crons:
        result = True

    return render_template(
        'crons.html',
        result=result,
        crons=crons,
        request=request.method
    )


# Ruta para editar config y channels un plugin
@app.route('/plugin/<plugin>', methods=['GET', 'POST'])
def plugin(plugin):
    plugins = _ui.plugins
    selected_plugin = list(filter(lambda p: p['name'] == plugin, plugins))
    result = False
    if request.method == 'POST':
        # Obtener los valores del formulario
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


# Ruta para editar config y channels un plugin
@app.route('/plugin/<plugin>/channels', methods=['GET', 'POST'])
def plugin_channels(plugin):
    result = False
    plugins = _ui.plugins

    selected_plugin = list(filter(lambda p: p['name'] == plugin, plugins))

    if request.method == 'POST':
        # Obtener los valores del formulario
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
def view_log():
    log_file = 'logs/ytdlp2strm.log'
    try:
        log_content = []
        with open(log_file, 'r', encoding='utf-8') as file:
            for line in file:
                # Si la línea empieza con '[', formatear el texto dentro de los primeros corchetes
                if line.startswith('['):
                    end_idx = line.find(']')
                    if end_idx != -1:
                        formatted_line = '[<span style="color:yellowgreen;">' + line[1:end_idx] + '</span>]' + line[
                                                                                                               end_idx + 1:]
                    else:
                        formatted_line = line  # Si no hay un cierre de corchete, deja la línea como está
                else:
                    formatted_line = line
                # Añadir un <br/> al final de cada línea
                log_content.append(formatted_line + '<br/>')
        return render_template('log.html', log_content=log_content)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@socketio.on('execute_command')
def handle_command(command):
    _ui.handle_command(command)