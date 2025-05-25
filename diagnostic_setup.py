#!/usr/bin/env python3
"""
ytdlp2STRM Authentication Setup Diagnostic
This script will help identify and fix secret key configuration issues.
"""

import os
import json
import secrets
import sys
from pathlib import Path
from datetime import datetime


def print_header():
    """Print diagnostic header"""
    print("🔐 ytdlp2STRM Authentication Setup Diagnostic")
    print("=" * 60)
    print(f"📅 Running at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Working directory: {os.getcwd()}")
    print(f"🐍 Python version: {sys.version.split()[0]}")
    print("=" * 60)


def check_directories():
    """Check and create required directories"""
    required_dirs = [
        'config',
        'logs',
        'ui',
        'ui/html',
        'ui/static',
        'plugins'
    ]

    print("🔍 Checking directory structure...")
    created_dirs = []

    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"  ✓ {dir_path}")
        else:
            try:
                os.makedirs(dir_path, exist_ok=True)
                created_dirs.append(dir_path)
                print(f"  ✓ {dir_path} (created)")
            except Exception as e:
                print(f"  ❌ {dir_path} (failed to create: {e})")

    if created_dirs:
        print(f"  📁 Created {len(created_dirs)} directories")

    return True


def check_config_file():
    """Check and fix config.json"""
    config_file = './config/config.json'

    print(f"\n🔍 Checking configuration file: {config_file}")

    if not os.path.exists(config_file):
        print("  ⚠ Config file not found, creating default...")
        config = create_default_config()
        return config

    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        print("  ✓ Config file loaded successfully")

        # Check for secret key
        config_updated = False
        if 'app_secret_key' not in config or not config['app_secret_key']:
            print("  ⚠ Secret key missing, generating new one...")
            config['app_secret_key'] = secrets.token_hex(32)
            config_updated = True
        else:
            key_len = len(config['app_secret_key'])
            if key_len < 32:
                print(f"  ⚠ Secret key too short ({key_len} chars), generating new one...")
                config['app_secret_key'] = secrets.token_hex(32)
                config_updated = True
            else:
                print(f"  ✓ Secret key found (length: {key_len})")

        # Check for required auth settings
        required_auth_settings = {
            'auth_max_attempts': 5,
            'auth_lockout_time': 300,
            'auth_captcha_threshold': 3,
            'auth_session_timeout': 7200,
            'auth_enable_captcha': True,
            'auth_log_events': True
        }

        missing_settings = []
        for key, default_value in required_auth_settings.items():
            if key not in config:
                config[key] = default_value
                missing_settings.append(key)
                config_updated = True

        if missing_settings:
            print(f"  ⚠ Added missing auth settings: {', '.join(missing_settings)}")

        # Check for user accounts
        if 'admins' not in config or not config['admins']:
            print("  ⚠ No admin accounts found, creating default admin...")
            config['admins'] = {
                'admin': {
                    'password': 'password123',
                    'role': 'admin',
                    'created': datetime.now().isoformat(),
                    'description': 'Default administrator - CHANGE PASSWORD!'
                }
            }
            config_updated = True

        if 'users' not in config or not config['users']:
            print("  ⚠ No user accounts found, creating default user...")
            config['users'] = {
                'user': {
                    'password': 'userpass',
                    'role': 'user',
                    'created': datetime.now().isoformat(),
                    'description': 'Default user - CHANGE PASSWORD!'
                }
            }
            config_updated = True

        # Save config if updated
        if config_updated:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print("  ✓ Configuration updated and saved")

        return config

    except json.JSONDecodeError as e:
        print(f"  ❌ Invalid JSON in config file: {e}")
        backup_file = f"{config_file}.backup.{int(datetime.now().timestamp())}"
        try:
            os.rename(config_file, backup_file)
            print(f"  📁 Corrupted config backed up to: {backup_file}")
        except Exception as be:
            print(f"  ⚠ Could not backup corrupted file: {be}")

        config = create_default_config()
        return config
    except Exception as e:
        print(f"  ❌ Error reading config file: {e}")
        return None


def create_default_config():
    """Create a complete default configuration"""
    config_file = './config/config.json'

    default_config = {
        "_comment": "ytdlp2STRM Configuration with Authentication",
        "_created": datetime.now().isoformat(),
        "_version": "2.0.0",

        # Application settings
        "ytdlp2strm_host": "0.0.0.0",
        "ytdlp2strm_port": 5000,
        "ytdlp2strm_keep_old_strm": "True",
        "ytdlp2strm_temp_file_duration": 86400,
        "cookies": "none",
        "cookie_value": "",
        "log_level": "INFO",

        # Authentication settings
        "app_secret_key": secrets.token_hex(32),
        "auth_max_attempts": 5,
        "auth_lockout_time": 300,
        "auth_captcha_threshold": 3,
        "auth_base_delay": 2000,
        "auth_session_timeout": 7200,
        "auth_enable_captcha": True,
        "auth_log_events": True,

        # User accounts
        "admins": {
            "admin": {
                "password": "password123",
                "role": "admin",
                "created": datetime.now().isoformat(),
                "description": "Default administrator - CHANGE PASSWORD IMMEDIATELY!"
            }
        },
        "users": {
            "user": {
                "password": "userpass",
                "role": "user",
                "created": datetime.now().isoformat(),
                "description": "Default user - CHANGE PASSWORD!"
            }
        }
    }

    try:
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        print(f"  ✓ Default configuration created: {config_file}")
        print(
            f"  🔑 Generated secret key: {default_config['app_secret_key'][:16]}...{default_config['app_secret_key'][-16:]}")
        return default_config
    except Exception as e:
        print(f"  ❌ Failed to create default config: {e}")
        return None


def check_locked_json():
    """Check and create logs/locked.json"""
    locked_file = './logs/locked.json'

    print(f"\n🔍 Checking lockout file: {locked_file}")

    if not os.path.exists(locked_file):
        print("  ⚠ Lockout file not found, creating default...")

        default_locked = {
            "_comment": "IP Address Lockout Tracking",
            "_created": datetime.now().isoformat(),
            "locked_ip_addresses": [],
            "lockout_history": [],
            "settings": {
                "max_history_entries": 1000,
                "auto_cleanup_on_startup": True,
                "log_unlocks": True
            },
            "statistics": {
                "total_lockouts": 0,
                "total_unlocks": 0,
                "most_locked_ip": None,
                "last_cleanup": None
            },
            "last_updated": datetime.now().isoformat()
        }

        try:
            with open(locked_file, 'w') as f:
                json.dump(default_locked, f, indent=4)
            print("  ✓ Default lockout file created")
            return True
        except Exception as e:
            print(f"  ❌ Failed to create lockout file: {e}")
            return False
    else:
        try:
            with open(locked_file, 'r') as f:
                locked_data = json.load(f)
            print("  ✓ Lockout file is valid")

            # Check structure
            if 'locked_ip_addresses' not in locked_data:
                locked_data['locked_ip_addresses'] = []
                with open(locked_file, 'w') as f:
                    json.dump(locked_data, f, indent=4)
                print("  ✓ Fixed lockout file structure")

            locked_count = len(locked_data.get('locked_ip_addresses', []))
            print(f"  📊 Currently locked IPs: {locked_count}")
            return True

        except json.JSONDecodeError as e:
            print(f"  ❌ Invalid JSON in lockout file: {e}")
            backup_file = f"{locked_file}.backup.{int(datetime.now().timestamp())}"
            try:
                os.rename(locked_file, backup_file)
                print(f"  📁 Corrupted file backed up to: {backup_file}")
            except Exception as be:
                print(f"  ⚠ Could not backup corrupted file: {be}")

            # Create new default
            default_locked = {
                "locked_ip_addresses": [],
                "last_updated": datetime.now().isoformat()
            }
            try:
                with open(locked_file, 'w') as f:
                    json.dump(default_locked, f, indent=4)
                print("  ✓ New lockout file created")
                return True
            except Exception as e:
                print(f"  ❌ Failed to create new lockout file: {e}")
                return False


def check_required_files():
    """Check for required authentication files"""
    required_files = {
        'ui/__init__.py': 'UI module init file',
        'ui/auth.py': 'Authentication system',
        'ui/routes.py': 'UI routes with authentication',
        'ui/ui.py': 'UI class',
        'ui/html/login.html': 'Login page template',
        'ui/html/general_settings.html': 'Settings page with auth config',
        'config/routes.py': 'Route registration with auth setup'
    }

    print("\n🔍 Checking required authentication files...")

    missing_files = []
    existing_files = []

    for file_path, description in required_files.items():
        if os.path.exists(file_path):
            # Check file size
            size = os.path.getsize(file_path)
            if size > 0:
                print(f"  ✓ {file_path} ({description}) - {size} bytes")
                existing_files.append(file_path)
            else:
                print(f"  ⚠ {file_path} ({description}) - EMPTY FILE")
                missing_files.append((file_path, description))
        else:
            print(f"  ❌ {file_path} ({description}) - MISSING")
            missing_files.append((file_path, description))

    print(f"  📊 Found {len(existing_files)}/{len(required_files)} required files")

    if missing_files:
        print(f"\n⚠ Missing {len(missing_files)} required files:")
        for file_path, description in missing_files:
            print(f"   - {file_path}: {description}")
        return False

    return True


def check_python_dependencies():
    """Check required Python packages"""
    required_packages = {
        'flask': 'Web framework',
        'bcrypt': 'Password hashing'
    }

    optional_packages = {
        'flask_socketio': 'Real-time communication',
        'secrets': 'Secure random generation (built-in Python 3.6+)'
    }

    print("\n🔍 Checking Python dependencies...")

    missing_required = []
    missing_optional = []

    # Check required packages
    for package, description in required_packages.items():
        try:
            if package == 'secrets':
                import secrets
            else:
                __import__(package)
            print(f"  ✓ {package} ({description})")
        except ImportError:
            print(f"  ❌ {package} ({description}) - NOT INSTALLED")
            missing_required.append(package)

    # Check optional packages
    for package, description in optional_packages.items():
        try:
            if package == 'secrets':
                import secrets
            else:
                __import__(package)
            print(f"  ✓ {package} ({description}) - optional")
        except ImportError:
            print(f"  ⚠ {package} ({description}) - optional, not installed")
            missing_optional.append(package)

    if missing_required:
        print(f"\n❌ Missing {len(missing_required)} REQUIRED packages:")
        for package in missing_required:
            print(f"   pip install {package}")
        return False

    if missing_optional:
        print(f"\n⚠ Missing {len(missing_optional)} optional packages (recommended):")
        for package in missing_optional:
            print(f"   pip install {package}")

    return True


def test_secret_key_generation():
    """Test secret key generation"""
    print("\n🔍 Testing secret key generation...")

    try:
        test_key = secrets.token_hex(32)
        print(f"  ✓ Generated test key: {test_key[:16]}...{test_key[-16:]}")
        print(f"  ✓ Key length: {len(test_key)} characters")

        # Test different lengths
        for length in [16, 32, 64]:
            key = secrets.token_hex(length)
            print(f"  ✓ {length}-byte key: {len(key)} chars")

        return True
    except Exception as e:
        print(f"  ❌ Failed to generate secret key: {e}")
        return False


def test_flask_import():
    """Test Flask import and basic setup"""
    print("\n🔍 Testing Flask setup...")

    try:
        from flask import Flask
        print("  ✓ Flask import successful")

        # Test basic Flask app creation
        test_app = Flask(__name__)
        test_app.secret_key = 'test-key'
        print("  ✓ Flask app creation successful")
        print("  ✓ Secret key assignment successful")

        return True
    except Exception as e:
        print(f"  ❌ Flask setup failed: {e}")
        return False


def check_file_permissions():
    """Check file permissions"""
    print("\n🔍 Checking file permissions...")

    files_to_check = [
        './config/config.json',
        './logs/locked.json'
    ]

    permission_issues = []

    for file_path in files_to_check:
        if os.path.exists(file_path):
            try:
                # Test read permission
                with open(file_path, 'r') as f:
                    f.read(1)

                # Test write permission
                with open(file_path, 'a') as f:
                    pass

                print(f"  ✓ {file_path} - read/write OK")
            except PermissionError:
                print(f"  ❌ {file_path} - permission denied")
                permission_issues.append(file_path)
            except Exception as e:
                print(f"  ⚠ {file_path} - {e}")
        else:
            print(f"  ⚠ {file_path} - does not exist")

    return len(permission_issues) == 0


def generate_startup_script():
    """Generate a startup script with proper error handling"""
    startup_script = '''#!/usr/bin/env python3
"""
ytdlp2STRM Startup Script with Authentication
Auto-generated by diagnostic tool
"""

import sys
import os

def check_config():
    """Quick config check before startup"""
    config_file = './config/config.json'
    if not os.path.exists(config_file):
        print("❌ Config file not found. Run diagnostic_setup.py first!")
        return False

    try:
        import json
        with open(config_file, 'r') as f:
            config = json.load(f)

        if 'app_secret_key' not in config:
            print("❌ Secret key not found in config. Run diagnostic_setup.py!")
            return False

        print("✓ Configuration looks good")
        return True
    except Exception as e:
        print(f"❌ Config error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting ytdlp2STRM with Authentication...")

    if not check_config():
        print("\\n🔧 Run this first: python diagnostic_setup.py")
        sys.exit(1)

    try:
        import main
    except Exception as e:
        print(f"❌ Startup failed: {e}")
        print("\\n🔧 Check the logs and run diagnostic_setup.py")
        sys.exit(1)
'''

    try:
        with open('start_secure.py', 'w') as f:
            f.write(startup_script)
        print("\n📝 Created startup script: start_secure.py")
        print("   Usage: python start_secure.py")
        return True
    except Exception as e:
        print(f"\n❌ Failed to create startup script: {e}")
        return False


def main():
    """Main diagnostic function"""
    print_header()

    # Run all checks
    checks = []

    # Check directories
    checks.append(("Directories", check_directories()))

    # Check Python dependencies
    checks.append(("Dependencies", check_python_dependencies()))

    # Check configuration
    config = check_config_file()
    checks.append(("Configuration", config is not None))

    # Check lockout file
    checks.append(("Lockout File", check_locked_json()))

    # Check required files
    checks.append(("Required Files", check_required_files()))

    # Test secret key generation
    checks.append(("Secret Key Test", test_secret_key_generation()))

    # Test Flask import
    checks.append(("Flask Test", test_flask_import()))

    # Check file permissions
    checks.append(("File Permissions", check_file_permissions()))

    # Generate startup script
    checks.append(("Startup Script", generate_startup_script()))

    # Summary
    print("\n" + "=" * 60)
    print("🔍 DIAGNOSTIC SUMMARY")
    print("=" * 60)

    passed_checks = sum(1 for _, status in checks if status)
    total_checks = len(checks)

    for check_name, status in checks:
        status_icon = "✅" if status else "❌"
        print(f"{status_icon} {check_name}")

    print(f"\n📊 Results: {passed_checks}/{total_checks} checks passed")

    if passed_checks == total_checks:
        print("\n🎉 All checks passed! Your authentication system should work.")
        print("\n🚀 Next steps:")
        print("   1. python start_secure.py")
        print("   2. Visit http://localhost:5000/login")
        print("   3. Login with: admin / password123")
        print("   4. Go to General Settings → Authentication")
        print("   5. Change default passwords immediately!")

        if config and 'app_secret_key' in config:
            print(f"\n🔑 Secret key: {config['app_secret_key'][:16]}...{config['app_secret_key'][-16:]}")

        print(f"\n📁 Configuration file: ./config/config.json")
        print(f"📁 Lockout tracking: ./logs/locked.json")

    else:
        failed_checks = total_checks - passed_checks
        print(f"\n❌ {failed_checks} issues found. Please fix the problems above.")
        print("\n🔧 Common solutions:")
        print("   - Install missing packages: pip install flask bcrypt")
        print("   - Create missing authentication files from setup guide")
        print("   - Check file permissions")
        print("   - Run this diagnostic again after fixes")

    print("\n📖 For detailed setup instructions, see the complete setup guide.")
    print("🆘 If you need help, check the troubleshooting section.")


if __name__ == "__main__":
    main()


def check_config_file():
    """Check and fix config.json"""
    config_file = './config/config.json'

    print(f"\n🔍 Checking configuration file: {config_file}")

    if not os.path.exists(config_file):
        print("  ⚠ Config file not found, creating default...")
        create_default_config()
        return

    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        print("  ✓ Config file loaded successfully")

        # Check for secret key
        if 'app_secret_key' not in config or not config['app_secret_key']:
            print("  ⚠ Secret key missing, generating new one...")
            config['app_secret_key'] = secrets.token_hex(32)

            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print("  ✓ Secret key added and saved")
        else:
            print(f"  ✓ Secret key found (length: {len(config['app_secret_key'])})")

        # Check for required auth settings
        required_auth_settings = {
            'auth_max_attempts': 5,
            'auth_lockout_time': 300,
            'auth_captcha_threshold': 3,
            'auth_session_timeout': 7200,
            'auth_enable_captcha': True,
            'auth_log_events': True
        }

        missing_settings = []
        for key, default_value in required_auth_settings.items():
            if key not in config:
                config[key] = default_value
                missing_settings.append(key)

        if missing_settings:
            print(f"  ⚠ Added missing auth settings: {', '.join(missing_settings)}")
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print("  ✓ Config updated and saved")

        # Check for user accounts
        if 'admins' not in config or not config['admins']:
            print("  ⚠ No admin accounts found, creating default admin...")
            config['admins'] = {
                'admin': {
                    'password': 'password123',
                    'role': 'admin',
                    'created': '2024-12-19T12:00:00.000Z',
                    'description': 'Default administrator - CHANGE PASSWORD!'
                }
            }

        if 'users' not in config or not config['users']:
            print("  ⚠ No user accounts found, creating default user...")
            config['users'] = {
                'user': {
                    'password': 'userpass',
                    'role': 'user',
                    'created': '2024-12-19T12:00:00.000Z',
                    'description': 'Default user - CHANGE PASSWORD!'
                }
            }

        if missing_settings or 'admins' not in config or 'users' not in config:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print("  ✓ User accounts added and saved")

        return config

    except json.JSONDecodeError as e:
        print(f"  ❌ Invalid JSON in config file: {e}")
        backup_file = f"{config_file}.backup"
        os.rename(config_file, backup_file)
        print(f"  📁 Corrupted config backed up to: {backup_file}")
        create_default_config()
        return
    except Exception as e:
        print(f"  ❌ Error reading config file: {e}")
        return None


def create_default_config():
    """Create a complete default configuration"""
    config_file = './config/config.json'

    default_config = {
        "_comment": "ytdlp2STRM Configuration with Authentication",
        "_created": "Auto-generated by diagnostic script",

        # Application settings
        "ytdlp2strm_host": "0.0.0.0",
        "ytdlp2strm_port": 5000,
        "ytdlp2strm_keep_old_strm": "True",
        "ytdlp2strm_temp_file_duration": 86400,
        "cookies": "none",
        "cookie_value": "",
        "log_level": "INFO",

        # Authentication settings
        "app_secret_key": secrets.token_hex(32),
        "auth_max_attempts": 5,
        "auth_lockout_time": 300,
        "auth_captcha_threshold": 3,
        "auth_base_delay": 2000,
        "auth_session_timeout": 7200,
        "auth_enable_captcha": True,
        "auth_log_events": True,

        # User accounts
        "admins": {
            "admin": {
                "password": "password123",
                "role": "admin",
                "created": "2024-12-19T12:00:00.000Z",
                "description": "Default administrator - CHANGE PASSWORD IMMEDIATELY!"
            }
        },
        "users": {
            "user": {
                "password": "userpass",
                "role": "user",
                "created": "2024-12-19T12:00:00.000Z",
                "description": "Default user - CHANGE PASSWORD!"
            }
        }
    }

    try:
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        print(f"  ✓ Default configuration created: {config_file}")
        return default_config
    except Exception as e:
        print(f"  ❌ Failed to create default config: {e}")
        return None


def check_locked_json():
    """Check and create logs/locked.json"""
    locked_file = './logs/locked.json'

    print(f"\n🔍 Checking lockout file: {locked_file}")

    if not os.path.exists(locked_file):
        print("  ⚠ Lockout file not found, creating default...")

        default_locked = {
            "_comment": "IP Address Lockout Tracking",
            "locked_ip_addresses": [],
            "lockout_history": [],
            "statistics": {
                "total_lockouts": 0,
                "total_unlocks": 0,
                "most_locked_ip": None,
                "last_cleanup": None
            },
            "last_updated": "2024-12-19T12:00:00.000Z"
        }

        try:
            with open(locked_file, 'w') as f:
                json.dump(default_locked, f, indent=4)
            print("  ✓ Default lockout file created")
        except Exception as e:
            print(f"  ❌ Failed to create lockout file: {e}")
    else:
        try:
            with open(locked_file, 'r') as f:
                json.load(f)
            print("  ✓ Lockout file is valid")
        except json.JSONDecodeError as e:
            print(f"  ❌ Invalid JSON in lockout file: {e}")
            backup_file = f"{locked_file}.backup"
            os.rename(locked_file, backup_file)
            print(f"  📁 Corrupted file backed up to: {backup_file}")

            # Create new default
            default_locked = {
                "locked_ip_addresses": [],
                "last_updated": "2024-12-19T12:00:00.000Z"
            }
            with open(locked_file, 'w') as f:
                json.dump(default_locked, f, indent=4)
            print("  ✓ New lockout file created")


def check_required_files():
    """Check for required authentication files"""
    required_files = {
        'ui/auth.py': 'Authentication system',
        'ui/html/login.html': 'Login page template',
        'ui/html/general_settings.html': 'Settings page with auth config'
    }

    print("\n🔍 Checking required authentication files...")

    missing_files = []
    for file_path, description in required_files.items():
        if os.path.exists(file_path):
            print(f"  ✓ {file_path} ({description})")
        else:
            print(f"  ❌ {file_path} ({description}) - MISSING")
            missing_files.append((file_path, description))

    if missing_files:
        print(f"\n⚠ Missing {len(missing_files)} required files:")
        for file_path, description in missing_files:
            print(f"   - {file_path}: {description}")
        print("\nPlease create these files according to the setup guide.")
        return False

    return True


def check_python_dependencies():
    """Check required Python packages"""
    required_packages = ['flask', 'bcrypt']

    print("\n🔍 Checking Python dependencies...")

    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ❌ {package} - NOT INSTALLED")
            missing_packages.append(package)

    if missing_packages:
        print(f"\n⚠ Missing {len(missing_packages)} required packages:")
        for package in missing_packages:
            print(f"   pip install {package}")
        return False

    return True


def test_secret_key_generation():
    """Test secret key generation"""
    print("\n🔍 Testing secret key generation...")

    try:
        test_key = secrets.token_hex(32)
        print(f"  ✓ Generated test key: {test_key[:16]}...{test_key[-16:]}")
        print(f"  ✓ Key length: {len(test_key)} characters")
        return True
    except Exception as e:
        print(f"  ❌ Failed to generate secret key: {e}")
        return False


def main():
    """Main diagnostic function"""
    print("🔐 ytdlp2STRM Authentication Setup Diagnostic")
    print("=" * 50)

    # Check directories
    check_directories()

    # Check Python dependencies
    deps_ok = check_python_dependencies()

    # Check configuration
    config = check_config_file()

    # Check lockout file
    check_locked_json()

    # Check required files
    files_ok = check_required_files()

    # Test secret key generation
    key_ok = test_secret_key_generation()

    # Summary
    print("\n" + "=" * 50)
    print("🔍 DIAGNOSTIC SUMMARY")
    print("=" * 50)

    if deps_ok and config and files_ok and key_ok:
        print("✅ All checks passed! Your authentication system should work.")
        print("\n🚀 Next steps:")
        print("   1. Start your application")
        print("   2. Visit http://localhost:5000/login")
        print("   3. Login with: admin / password123")
        print("   4. Change default passwords immediately!")

        if config and 'app_secret_key' in config:
            print(f"\n🔑 Secret key configured: {config['app_secret_key'][:16]}...{config['app_secret_key'][-16:]}")
    else:
        print("❌ Some issues found. Please fix the problems above.")
        print("\n🔧 Common solutions:")
        if not deps_ok:
            print("   - Install missing packages: pip install flask bcrypt")
        if not files_ok:
            print("   - Create missing authentication files")
        if not config:
            print("   - Fix configuration file issues")

    print("\n📖 For detailed setup instructions, see the setup guide.")


if __name__ == "__main__":
    main()
