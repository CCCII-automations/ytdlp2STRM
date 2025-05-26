import json
import shlex
import os
import re
import time  # Added for duplicate prevention
from clases.config import config as c
from clases.cron import cron as cron
from clases.log import log as l
from subprocess import Popen, PIPE, STDOUT
import threading

# Only import Flask-SocketIO if we're in a Flask context
try:
    from flask import has_request_context
    from flask_socketio import emit

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    has_request_context = lambda: False
    emit = lambda *args, **kwargs: None


class Ui:
    def __init__(self):
        self.config_file = 'config/config.json'
        self.plugins_file = 'config/plugins.py'
        self.crons_file = 'config/crons.json'

    @property
    def general_settings(self):
        # Read the configuration file
        data = []
        try:
            with open(self.config_file, 'r') as file:
                data = json.load(file)
        except FileNotFoundError:
            # Create default config if file doesn't exist
            data = {
                "output_path": "./output",
                "log_level": "INFO",
                "max_workers": 4,
                "download_format": "best"
            }
            self.general_settings = data
        return data

    @general_settings.setter
    def general_settings(self, data):
        # Save values to configuration file
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w') as file:
            json.dump(data, file, indent=4)

    @property
    def plugins_py(self):
        data = ""
        try:
            with open(self.plugins_file, 'r') as file:
                data = file.read()
        except FileNotFoundError:
            # Create default plugins.py if it doesn't exist
            data = "# Plugin imports - uncomment to enable\n# import plugins.youtube\n# import plugins.twitch\n# import plugins.generic"
            self.plugins_py = data
        return data

    @plugins_py.setter
    def plugins_py(self, data):
        os.makedirs(os.path.dirname(self.plugins_file), exist_ok=True)
        with open(self.plugins_file, 'w', newline="") as file:
            file.write(data)

    @property
    def plugins(self):
        plugins = []

        # Parse plugins.py to find available plugins
        plugins_content = self.plugins_py

        # Look for plugin import lines - handle your specific format
        for line in plugins_content.split('\n'):
            original_line = line
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Check if it's a plugin import line
            is_plugin_line = False
            plugin_name = None
            is_enabled = True

            # Handle different import formats
            if line.startswith('#'):
                is_enabled = False
                line = line[1:].strip()  # Remove the # and whitespace

            # Format: from plugins.pluginname import pluginname
            if line.startswith('from plugins.') and ' import ' in line:
                try:
                    parts = line.split(' import ')
                    if len(parts) == 2:
                        plugin_path = parts[0].replace('from plugins.', '')
                        plugin_name = plugin_path
                        is_plugin_line = True
                except:
                    continue

            # Format: import plugins.pluginname
            elif line.startswith('import plugins.'):
                try:
                    plugin_name = line.replace('import plugins.', '')
                    is_plugin_line = True
                except:
                    continue

            if is_plugin_line and plugin_name:
                # Build plugin path
                plugin_path = f'./plugins/{plugin_name}'

                # Try to load plugin config
                config_file = f'{plugin_path}/config.json'
                config_data = {}
                if os.path.exists(config_file):
                    try:
                        with open(config_file, 'r') as f:
                            config_data = json.load(f)
                    except:
                        config_data = {"name": plugin_name}
                else:
                    config_data = {"name": plugin_name}

                # Try to load channels - handle your specific structure
                channels_file = config_data.get('channels_list_file', f'{plugin_path}/channel_list.json')
                channels = []
                if os.path.exists(channels_file):
                    try:
                        with open(channels_file, 'r') as f:
                            channels_data = json.load(f)
                            # Handle both list format and object format
                            if isinstance(channels_data, list):
                                channels = channels_data
                            elif isinstance(channels_data, dict) and 'channels' in channels_data:
                                channels = channels_data['channels']
                    except:
                        channels = []

                plugin_info = {
                    'name': plugin_name,
                    'path': plugin_path,
                    'enabled': is_enabled,
                    'config': config_data,
                    'channels': channels,
                    'original_line': original_line.strip()
                }

                plugins.append(plugin_info)

        return plugins

    @plugins.setter
    def plugins(self, data):
        config_file = data['config_file']
        data.pop('config_file', None)

        os.makedirs(os.path.dirname(config_file), exist_ok=True)

        if 'channels' in data:
            # Handle channel list saving
            with open(config_file, 'w') as file:
                json.dump(data['channels'], file, indent=4)
        else:
            # Handle regular config saving
            with open(config_file, 'w') as file:
                json.dump(data, file, indent=4)

    @property
    def crons(self):
        data = []
        try:
            with open(self.crons_file, 'r') as file:
                data = json.load(file)
        except FileNotFoundError:
            # Create empty crons file if it doesn't exist
            data = []
            self.crons = json.dumps(data)
        return data

    @crons.setter
    def crons(self, data):
        os.makedirs(os.path.dirname(self.crons_file), exist_ok=True)
        with open(self.crons_file, 'w', newline="") as file:
            file.write(data)

    def get_available_plugins(self):
        """
        Scan the plugins directory to find all available plugins
        """
        available_plugins = []
        plugins_dir = './plugins'

        if os.path.exists(plugins_dir):
            for item in os.listdir(plugins_dir):
                plugin_path = os.path.join(plugins_dir, item)
                if os.path.isdir(plugin_path):
                    # Check if it has the required files
                    init_file = os.path.join(plugin_path, '__init__.py')
                    config_file = os.path.join(plugin_path, 'config.json')

                    if os.path.exists(init_file):
                        plugin_info = {
                            'name': item,
                            'path': plugin_path,
                            'has_config': os.path.exists(config_file),
                            'enabled': self.is_plugin_enabled(item)
                        }
                        available_plugins.append(plugin_info)

        return available_plugins

    def is_plugin_enabled(self, plugin_name):
        """
        Check if a plugin is enabled in plugins.py
        """
        plugins_content = self.plugins_py
        for line in plugins_content.split('\n'):
            if f'plugins.{plugin_name}' in line and not line.strip().startswith('#'):
                return True
        return False

    def enable_plugin(self, plugin_name):
        """
        Enable a plugin by uncommenting its import line
        """
        lines = self.plugins_py.split('\n')
        for i, line in enumerate(lines):
            if f'plugins.{plugin_name}' in line and line.strip().startswith('#'):
                lines[i] = line.lstrip('#').lstrip()
                self.plugins_py = '\n'.join(lines)
                return True
        return False

    def disable_plugin(self, plugin_name):
        """
        Disable a plugin by commenting its import line
        """
        lines = self.plugins_py.split('\n')
        for i, line in enumerate(lines):
            if f'plugins.{plugin_name}' in line and not line.strip().startswith('#'):
                lines[i] = f'# {line}'
                self.plugins_py = '\n'.join(lines)
                return True
        return False

    def safe_emit(self, event, data):
        """
        Safely emit to Flask-SocketIO only if we're in a request context
        """
        if FLASK_AVAILABLE and has_request_context():
            try:
                emit(event, data)
            except RuntimeError as e:
                # Log the error but don't fail
                l.log('ui', f'Cannot emit {event}: {str(e)}')
        else:
            # Just log the message if we can't emit
            l.log('ui', f'Would emit {event}: {data}')

    def handle_command(self, command):
        """
        Handle command execution with proper output streaming - prevent duplicates
        """
        # Check if this is a duplicate call by using a simple debouncing mechanism
        current_time = time.time()
        command_key = f"cmd_{hash(command)}"

        # Check if we've seen this exact command very recently (within 1 second)
        if hasattr(self, '_last_commands'):
            if command_key in self._last_commands:
                if current_time - self._last_commands[command_key] < 1.0:
                    l.log('ui', f'Ignoring duplicate command: "{command}"')
                    return
        else:
            self._last_commands = {}

        # Record this command execution
        self._last_commands[command_key] = current_time

        # Clean old entries (keep only last 10 commands)
        if len(self._last_commands) > 10:
            oldest_key = min(self._last_commands.keys(),
                             key=lambda k: self._last_commands[k])
            del self._last_commands[oldest_key]

        # Debug: Log the received command
        l.log('ui', f'Received command: "{command}"')

        # Send initial acknowledgment (safely)
        self.safe_emit('command_output', f'$ {command}')

        # Ensure Python runs unbuffered
        if 'python3' in command:
            command = command.replace('python3', 'python3 -u')
        elif 'python' in command:
            command = command.replace('python', 'python -u')

        # Debug: Log the modified command
        l.log('ui', f'Modified command: "{command}"')

        # Parse command
        secure_command = command.split(' ')
        l.log('ui', f'Split command: {secure_command}')

        try:
            # Validate command - allow both direct cli.py and full path
            if ('cli.py' in command and ('python' in command or 'python3' in command)):
                l.log('ui', 'Command validation passed, executing...')

                # Create environment with unbuffered output
                env = os.environ.copy()
                env['PYTHONUNBUFFERED'] = '1'

                # Start the process
                process = Popen(
                    shlex.split(command),
                    stdout=PIPE,
                    stderr=STDOUT,  # Combine stderr with stdout
                    text=True,
                    encoding='utf-8',
                    bufsize=1,  # Line buffered
                    env=env
                )

                # Function to read output in a separate thread
                def read_output():
                    try:
                        for line in iter(process.stdout.readline, ''):
                            if line:
                                line = line.rstrip()
                                l.log('ui', f'Output: {line}')
                                self.safe_emit('command_output', line)

                        # Wait for process to complete
                        process.wait()

                        if process.returncode == 0:
                            self.safe_emit('command_completed', {'data': 'Command completed successfully'})
                            l.log('ui', 'Command completed successfully')
                        else:
                            self.safe_emit('command_error', f'Command exited with code {process.returncode}')
                            l.log('ui', f'Command exited with code {process.returncode}')

                    except Exception as e:
                        error_msg = f'Error reading output: {str(e)}'
                        l.log('ui', error_msg)
                        self.safe_emit('command_error', error_msg)
                    finally:
                        if process.stdout:
                            process.stdout.close()

                # Start output reading thread
                output_thread = threading.Thread(target=read_output)
                output_thread.daemon = True
                output_thread.start()

            else:
                error_msg = f'Only python cli.py commands can be executed. Received: {command}'
                l.log('ui', error_msg)
                self.safe_emit('command_output', error_msg)
                self.safe_emit('command_completed', {'data': 'Invalid command'})

        except Exception as e:
            error_msg = f'Error executing command: {str(e)}'
            l.log('ui', error_msg)
            self.safe_emit('command_error', error_msg)
            self.safe_emit('command_completed', {'data': 'Command failed with errors'})