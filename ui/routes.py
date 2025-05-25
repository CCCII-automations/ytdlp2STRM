from __main__ import app
from flask import request, render_template, session, send_from_directory, jsonify
import json
import logging
import re
from clases.worker import worker as w
from ui.ui import Ui

_ui = Ui()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.WARNING)


@app.route('/')
def index():
    try:
        crons = _ui.crons
        return render_template('index.html', plugins=_ui.plugins, crons=crons)
    except Exception as e:
        logger.error(f"Failed to render index: {e}")
        return jsonify({'success': False, 'error': 'Failed to load index'}), 500


@app.route('/api/update-plugins', methods=['POST'])
def api_update_plugins():
    try:
        data = request.get_json()
        changes = data.get('changes', [])
        current_content = _ui.plugins_py
        lines = current_content.split('\n')

        for change in changes:
            plugin_name = change['name']
            should_enable = change['enabled']
            for i, line in enumerate(lines):
                if f'plugins.{plugin_name}' in line:
                    if should_enable and line.strip().startswith('#'):
                        lines[i] = line.lstrip('#').lstrip()
                    elif not should_enable and not line.strip().startswith('#'):
                        lines[i] = f'# {line}'
                    break

        _ui.plugins_py = '\n'.join(lines)
        logger.info("Plugins updated successfully")
        return jsonify({'success': True, 'message': 'Plugins updated successfully'})
    except Exception as e:
        logger.error(f"Failed to update plugins: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/status', methods=['GET'])
def api_status():
    try:
        plugins = _ui.plugins
        crons = _ui.crons
        stats = {
            'total_plugins': len(plugins),
            'active_plugins': len([p for p in plugins if p.get('enabled', False)]),
            'total_channels': sum(len(p.get('channels', [])) for p in plugins if p.get('channels')),
            'total_crons': len(crons)
        }
        logger.info("Status fetched successfully")
        return jsonify({'success': True, 'stats': stats, 'plugins': plugins, 'crons': crons})
    except Exception as e:
        logger.error(f"Failed to fetch status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/run-plugin/<plugin_name>', methods=['POST'])
def api_run_plugin(plugin_name):
    try:
        plugins = _ui.plugins
        plugin = next((p for p in plugins if p['name'] == plugin_name), None)

        if not plugin:
            logger.warning(f"Plugin not found: {plugin_name}")
            return jsonify({'success': False, 'error': 'Plugin not found'}), 404

        if not plugin.get('enabled', False):
            logger.warning(f"Plugin is disabled: {plugin_name}")
            return jsonify({'success': False, 'error': 'Plugin is disabled'}), 400

        command = f"python3 cli.py --media {plugin_name}"
        logger.info(f"Executing plugin command: {command}")
        return jsonify({'success': True, 'message': f'Plugin {plugin_name} execution started', 'command': command})
    except Exception as e:
        logger.error(f"Failed to run plugin {plugin_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/general', methods=['GET', 'POST'])
def general_settings():
    result = False
    if request.method == 'POST':
        try:
            config_data = {key: value for key, value in request.form.items()}
            _ui.general_settings = config_data
            result = True
            logger.info("General settings updated")
        except Exception as e:
            logger.error(f"Failed to update general settings: {e}")

    return render_template('general_settings.html', config_data=_ui.general_settings, result=result, request=request.method)


@app.route('/plugins', methods=['GET', 'POST'])
def plugin_py_settings():
    result = False
    if request.method == 'POST':
        try:
            plugin_code = request.form.getlist('plugin_field')
            _ui.plugins_py = '\n'.join(plugin_code)
            result = True
            logger.info("Plugin code updated")
        except Exception as e:
            logger.error(f"Failed to update plugin code: {e}")

    return render_template('plugin_py_settings.html', result=result, plugin_code=_ui.plugins_py.splitlines(), request=request.method)


@app.route('/crons', methods=['GET', 'POST'])
def crons_settings():
    result = False
    if request.method == 'POST':
        try:
            headers = ('every', 'qty', 'at', 'timezone', 'plugin', 'param')
            values = tuple(request.form.getlist(f'{h}[]') for h in headers)
            crons = [{} for _ in range(len(values[0]))]
            for x, i in enumerate(values):
                for _x, _i in enumerate(i):
                    if headers[x] == 'plugin':
                        crons[_x]['do'] = ['--media', _i]
                    elif headers[x] == 'param':
                        crons[_x]['do'].append('--param')
                        crons[_x]['do'].append(_i)
                    else:
                        crons[_x][headers[x]] = _i
            _ui.crons = json.dumps(crons)
            result = True
            logger.info("Crons updated successfully")
        except Exception as e:
            logger.error(f"Failed to update crons: {e}")

    return render_template('crons.html', result=result, crons=_ui.crons, request=request.method)


@app.route('/plugin/<plugin>', methods=['GET', 'POST'])
def plugin(plugin):
    result = False
    try:
        plugins = _ui.plugins
        selected_plugin = [p for p in plugins if p['name'] == plugin]
        if request.method == 'POST':
            config_data = {key: value for key, value in request.form.items()}
            config_data['config_file'] = f'./plugins/{plugin}/config.json'
            _ui.plugins = config_data
            result = True
            plugins = _ui.plugins
            selected_plugin = [p for p in plugins if p['name'] == plugin]
            logger.info(f"Updated config for plugin: {plugin}")
        return render_template('plugin_settings.html', plugin=selected_plugin[0], result=result, request=request.method)
    except Exception as e:
        logger.error(f"Failed to manage plugin config for {plugin}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/plugin/<plugin>/channels', methods=['GET', 'POST'])
def plugin_channels(plugin):
    result = False
    try:
        plugins = _ui.plugins
        selected_plugin = [p for p in plugins if p['name'] == plugin]
        if request.method == 'POST':
            config_data = {
                'config_file': f'./plugins/{plugin}/channel_list.json',
                'channels': request.form.getlist('channels')
            }
            _ui.plugins = config_data
            result = bool(config_data['channels'])
            plugins = _ui.plugins
            selected_plugin = [p for p in plugins if p['name'] == plugin]
            logger.info(f"Updated channels for plugin: {plugin}")
        return render_template('plugin_channels.html', plugin=selected_plugin[0], result=result, request=request.method)
    except Exception as e:
        logger.error(f"Failed to manage channels for plugin {plugin}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/log')
def view_log():
    log_file = 'logs/ytdlp2strm.log'
    try:
        with open(log_file, 'r', encoding='utf-8') as file:
            log_content = []
            for line in file:
                if line.startswith('['):
                    end_idx = line.find(']')
                    if end_idx != -1:
                        formatted_line = '[<span style="color:yellowgreen;">' + line[1:end_idx] + '</span>]' + line[end_idx + 1:]
                    else:
                        formatted_line = line
                else:
                    formatted_line = line
                log_content.append(formatted_line + '<br/>')
        logger.info("Log file rendered successfully")
        return render_template('log.html', log_content=log_content)
    except Exception as e:
        logger.error(f"Failed to read log file: {e}")
        return jsonify({'status': 'error', 'message': str(e)})
