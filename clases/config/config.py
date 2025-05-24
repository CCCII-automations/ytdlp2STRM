import json
import os
import shutil
from pathlib import Path

from clases.log import log as l


class config:
    def __init__(self, config_file=None):
        # Get the app base directory first
        self.app_base_dir = self._get_app_base_dir()

        # Handle config file path
        if config_file is None:
            # Default config file in the config directory
            self.config_file = self.app_base_dir / "config" / "config.json"
        elif isinstance(config_file, str):
            config_path = Path(config_file)
            if config_path.is_absolute():
                # Absolute path provided
                self.config_file = config_path
            else:
                # Relative path - make it relative to app base dir
                self.config_file = self.app_base_dir / config_path
        else:
            self.config_file = Path(config_file)

    def _get_app_base_dir(self):
        """
        Get the application base directory regardless of where the script is run from.
        Uses multiple fallback methods for maximum reliability.
        """
        try:
            # Method 1: Environment variable
            if "APP_BASE_DIR" in os.environ:
                app_dir = Path(os.environ["APP_BASE_DIR"])
                if app_dir.exists():
                    return app_dir

            # Method 2: Look for ytdlp2STRM directory in parent hierarchy
            current_path = Path(__file__).resolve()
            for parent in [current_path] + list(current_path.parents):
                if parent.name == "ytdlp2STRM":
                    return parent

            # Method 3: Look for marker files (cli.py, config directory, etc.)
            current_path = Path(__file__).resolve().parent
            marker_files = ['cli.py', 'config', 'requirements.txt']

            while current_path != current_path.parent:
                for marker in marker_files:
                    if (current_path / marker).exists():
                        return current_path
                current_path = current_path.parent

            # Method 4: Check common installation locations
            common_paths = [
                Path("/opt/ytdlp2STRM"),
                Path.home() / "ytdlp2STRM",
                Path.cwd() / "ytdlp2STRM"
            ]

            for path in common_paths:
                if path.exists() and (path / "config").exists():
                    return path

            # Fallback: use current working directory
            return Path.cwd()

        except Exception as e:
            l.log("config", f"Error finding app base directory: {e}")
            return Path("/opt/ytdlp2STRM")  # Hard fallback

    def get_app_base_dir(self):
        """Public method to get the app base directory"""
        return self.app_base_dir

    def get_config_path(self, relative_path):
        """Get absolute path for any file relative to app base directory"""
        return self.app_base_dir / relative_path

    def _load_config_file(self, config_file_path):
        """
        Load configuration from file with example file fallback.
        Extracted to avoid code duplication.
        """
        config_file_path = Path(config_file_path)

        # Check if config file exists
        if config_file_path.exists():
            try:
                with open(config_file_path, "r") as file:
                    return json.load(file)
            except (json.JSONDecodeError, IOError) as e:
                l.log("config", f"Error reading config file {config_file_path}: {e}")
                return None
        else:
            # Generate example config file name
            example_config_file = config_file_path.parent / (config_file_path.stem + ".example.json")

            # Check if example file exists
            if example_config_file.exists():
                log_text = f"No {config_file_path} detected, Building a copy from {example_config_file}. Please check this in config folder"
                l.log("config", log_text)

                try:
                    # Ensure the config directory exists
                    config_file_path.parent.mkdir(parents=True, exist_ok=True)

                    # Copy example to actual config
                    shutil.copyfile(example_config_file, config_file_path)

                    # Read the newly created config file
                    with open(config_file_path, "r") as file:
                        return json.load(file)

                except (IOError, json.JSONDecodeError) as e:
                    l.log("config", f"Error creating/reading config from example: {e}")
                    return None
            else:
                l.log("config", f"Neither config file {config_file_path} nor example file {example_config_file} found")
                return None

    def get_config(self):
        """Get the main configuration"""
        return self._load_config_file(self.config_file)

    def get_channels(self):
        """Get channels configuration (same as get_config for now)"""
        return self._load_config_file(self.config_file)

    def get_config_for_file(self, config_filename):
        """Get configuration from a specific file in the config directory"""
        config_path = self.app_base_dir / "config" / config_filename
        return self._load_config_file(config_path)

    def save_config(self, config_data, config_filename=None):
        """Save configuration to file"""
        if config_filename is None:
            save_path = self.config_file
        else:
            save_path = self.app_base_dir / "config" / config_filename

        try:
            # Ensure directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "w") as file:
                json.dump(config_data, file, indent=4)

            l.log("config", f"Configuration saved to {save_path}")
            return True

        except IOError as e:
            l.log("config", f"Error saving config to {save_path}: {e}")
            return False