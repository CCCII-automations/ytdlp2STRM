# =============================================================================
# ui/auth.py - Enhanced Authentication System with IP Whitelist Implementation
# =============================================================================

import time
import json
import os
import bcrypt
import ipaddress
from datetime import datetime, timedelta
from functools import wraps
from flask import session, request, redirect, url_for, jsonify, render_template
import logging

logger = logging.getLogger(__name__)


class AuthManager:
    """Enhanced Authentication and security manager for ytdlp2STRM with IP whitelist support"""

    def __init__(self):
        self.config_file = './config/config.json'
        self.locked_file = './logs/locked.json'

        # Load configuration
        self.config = self.load_config()

        # Security settings from config
        self.max_attempts = self.config.get('auth_max_attempts', 5)
        self.lockout_time = self.config.get('auth_lockout_time', 300)  # 5 minutes
        self.captcha_threshold = self.config.get('auth_captcha_threshold', 3)
        self.base_delay = self.config.get('auth_base_delay', 2000)  # 2 seconds
        self.session_timeout = self.config.get('auth_session_timeout', 7200)  # 2 hours

        # IP whitelist settings
        self.enable_ip_whitelist = self.config.get('security_settings', {}).get('rate_limiting', {}).get(
            'enable_ip_whitelist', False)
        self.ip_whitelist_raw = self.config.get('security_settings', {}).get('rate_limiting', {}).get('ip_whitelist',
                                                                                                      [])
        self.ip_whitelist = self.parse_ip_whitelist(self.ip_whitelist_raw)

        # In-memory storage for failed attempts (reset on restart)
        self.failed_attempts = {}
        self.security_logs = []

        # Ensure logs directory exists
        os.makedirs('./logs', exist_ok=True)

        # Clean up expired locks on startup
        self.cleanup_expired_locks()

        # Log IP whitelist status
        if self.enable_ip_whitelist:
            logger.info(f"✓ IP Whitelist enabled with {len(self.ip_whitelist)} entries")
            for ip_entry in self.ip_whitelist_raw:
                logger.info(f"  - Whitelisted: {ip_entry}")
        else:
            logger.info("✓ IP Whitelist disabled - all IPs subject to rate limiting")

    def parse_ip_whitelist(self, whitelist_raw):
        """Parse IP whitelist entries into network objects"""
        parsed_whitelist = []

        if not whitelist_raw:
            return parsed_whitelist

        for ip_entry in whitelist_raw:
            try:
                # Handle both single IPs and CIDR notation
                if '/' in ip_entry:
                    # CIDR notation (e.g., "192.168.1.0/24")
                    network = ipaddress.ip_network(ip_entry, strict=False)
                    parsed_whitelist.append(network)
                else:
                    # Single IP address
                    ip = ipaddress.ip_address(ip_entry)
                    # Convert single IP to /32 or /128 network
                    if ip.version == 4:
                        network = ipaddress.IPv4Network(f"{ip}/32")
                    else:
                        network = ipaddress.IPv6Network(f"{ip}/128")
                    parsed_whitelist.append(network)

                logger.debug(f"Parsed whitelist entry: {ip_entry} -> {network}")

            except ValueError as e:
                logger.error(f"Invalid IP whitelist entry '{ip_entry}': {e}")
                continue

        return parsed_whitelist

    def is_ip_whitelisted(self, ip_address):
        """Check if an IP address is in the whitelist"""
        if not self.enable_ip_whitelist:
            return False  # Whitelist disabled, no IPs are whitelisted

        if not self.ip_whitelist:
            return False  # Empty whitelist

        try:
            client_ip = ipaddress.ip_address(ip_address)

            for network in self.ip_whitelist:
                if client_ip in network:
                    logger.debug(f"IP {ip_address} matches whitelist entry: {network}")
                    return True

            logger.debug(f"IP {ip_address} not found in whitelist")
            return False

        except ValueError as e:
            logger.error(f"Invalid IP address '{ip_address}': {e}")
            return False

    def should_skip_rate_limiting(self, ip_address):
        """Determine if rate limiting should be skipped for this IP"""
        if self.is_ip_whitelisted(ip_address):
            logger.info(f"Skipping rate limiting for whitelisted IP: {ip_address}")
            return True
        return False

    def load_config(self):
        """Load configuration from config.json"""
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {self.config_file} not found, using defaults")
            return self.create_default_config()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return self.create_default_config()

    def save_config(self, config):
        """Save configuration to config.json"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
            logger.info("Configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False

    def create_default_config(self):
        """Create default configuration with authentication settings"""
        default_config = {
            # Existing ytdlp2strm settings
            "ytdlp2strm_host": "0.0.0.0",
            "ytdlp2strm_port": 5000,
            "ytdlp2strm_keep_old_strm": "True",
            "ytdlp2strm_temp_file_duration": 86400,
            "cookies": "none",
            "cookie_value": "",
            "log_level": "INFO",

            # New authentication settings
            "app_secret_key": self.generate_secret_key(),
            "auth_max_attempts": 5,
            "auth_lockout_time": 300,
            "auth_captcha_threshold": 3,
            "auth_base_delay": 2000,
            "auth_session_timeout": 7200,
            "auth_enable_captcha": True,
            "auth_log_events": True,

            # Security settings with IP whitelist
            "security_settings": {
                "rate_limiting": {
                    "enable_ip_whitelist": False,
                    "ip_whitelist": [
                        "127.0.0.1",
                        "::1"
                    ],
                    "enable_progressive_delay": True,
                    "max_delay_seconds": 60,
                    "cleanup_interval": 900
                }
            },

            # User accounts
            "admins": {
                "admin": {
                    "password": self.hash_password("password123"),
                    "role": "admin",
                    "created": datetime.now().isoformat()
                }
            },
            "users": {
                "user": {
                    "password": self.hash_password("userpass"),
                    "role": "user",
                    "created": datetime.now().isoformat()
                }
            }
        }

        # Save default config
        self.save_config(default_config)
        return default_config

    def generate_secret_key(self):
        """Generate a secure secret key"""
        import secrets
        return secrets.token_hex(32)

    def hash_password(self, password):
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def verify_password(self, password, hashed):
        """Verify password against bcrypt hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    def load_locked_ips(self):
        """Load locked IPs from locked.json"""
        try:
            with open(self.locked_file, 'r') as f:
                data = json.load(f)
                return data.get('locked_ip_addresses', [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_locked_ips(self, locked_ips):
        """Save locked IPs to locked.json"""
        try:
            data = {
                'locked_ip_addresses': locked_ips,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.locked_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save locked IPs: {e}")

    def cleanup_expired_locks(self):
        """Clean up expired IP locks"""
        locked_ips = self.load_locked_ips()
        current_time = time.time()

        # Filter out expired locks
        active_locks = []
        for lock in locked_ips:
            if current_time < lock.get('time_locked', 0) + self.lockout_time:
                active_locks.append(lock)
            else:
                logger.info(f"Removing expired lock for IP: {lock.get('ip')}")

        # Save cleaned up list
        if len(active_locks) != len(locked_ips):
            self.save_locked_ips(active_locks)

        return active_locks

    def is_ip_locked(self, ip_address):
        """Check if IP address is locked (respects whitelist)"""
        # Check if IP is whitelisted - whitelisted IPs cannot be locked
        if self.is_ip_whitelisted(ip_address):
            logger.debug(f"IP {ip_address} is whitelisted, cannot be locked")
            return False, 0

        locked_ips = self.cleanup_expired_locks()
        current_time = time.time()

        for lock in locked_ips:
            if (lock.get('ip') == ip_address and
                    current_time < lock.get('time_locked', 0) + self.lockout_time):
                return True, lock.get('time_locked', 0) + self.lockout_time

        return False, 0

    def lock_ip(self, ip_address, reason="Multiple failed login attempts"):
        """Lock an IP address (respects whitelist)"""
        # Never lock whitelisted IPs
        if self.is_ip_whitelisted(ip_address):
            logger.warning(f"Attempted to lock whitelisted IP {ip_address} - action blocked")
            self.log_security_event('whitelist_protection',
                                    f'IP {ip_address} protected from lockout by whitelist',
                                    ip_address)
            return False

        locked_ips = self.load_locked_ips()
        current_time = time.time()

        # Remove existing lock for this IP if present
        locked_ips = [lock for lock in locked_ips if lock.get('ip') != ip_address]

        # Add new lock
        new_lock = {
            'ip': ip_address,
            'time_locked': current_time,
            'reason': reason,
            'expires_at': current_time + self.lockout_time
        }
        locked_ips.append(new_lock)

        self.save_locked_ips(locked_ips)
        self.log_security_event('ip_locked', f'IP {ip_address} locked: {reason}', ip_address)

        logger.warning(f"IP {ip_address} locked for {self.lockout_time} seconds: {reason}")
        return True

    def log_security_event(self, event_type, details, ip_address, username=None):
        """Log security events for monitoring"""
        if not self.config.get('auth_log_events', True):
            return

        # Add whitelist status to security events
        whitelisted = self.is_ip_whitelisted(ip_address) if self.enable_ip_whitelist else False

        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'details': details,
            'ip': ip_address,
            'ip_whitelisted': whitelisted,
            'username': username,
            'user_agent': request.headers.get('User-Agent', 'Unknown')[:100]
        }
        self.security_logs.append(event)

        # Keep only last 1000 events in memory
        if len(self.security_logs) > 1000:
            self.security_logs = self.security_logs[-1000:]

        whitelist_status = " [WHITELISTED]" if whitelisted else ""
        logger.info(f"SECURITY EVENT [{event_type}]: {details} - IP: {ip_address}{whitelist_status} - User: {username}")

    def check_rate_limit(self, username, ip_address):
        """Check and update rate limiting (respects whitelist)"""
        # Skip rate limiting for whitelisted IPs
        if self.should_skip_rate_limiting(ip_address):
            return 0

        key = f"{username}:{ip_address}"
        current_time = time.time()

        if key not in self.failed_attempts:
            self.failed_attempts[key] = {'count': 0, 'last_attempt': current_time}

        attempt_data = self.failed_attempts[key]

        # Reset counter if more than 15 minutes passed
        if current_time - attempt_data['last_attempt'] > 900:  # 15 minutes
            attempt_data['count'] = 0

        return attempt_data['count']

    def record_failed_attempt(self, username, ip_address):
        """Record failed login attempt (respects whitelist)"""
        # Skip recording for whitelisted IPs
        if self.should_skip_rate_limiting(ip_address):
            self.log_security_event('failed_login_whitelisted',
                                    f'Failed login from whitelisted IP - no penalty applied',
                                    ip_address, username)
            return

        key = f"{username}:{ip_address}"
        current_time = time.time()

        if key not in self.failed_attempts:
            self.failed_attempts[key] = {'count': 0, 'last_attempt': current_time}

        self.failed_attempts[key]['count'] += 1
        self.failed_attempts[key]['last_attempt'] = current_time

        # Lock IP after max attempts (only for non-whitelisted IPs)
        if self.failed_attempts[key]['count'] >= self.max_attempts:
            self.lock_ip(ip_address, f'Failed login attempts for user: {username}')

    def verify_credentials(self, username, password):
        """Verify user credentials against config"""
        # Check admins
        admins = self.config.get('admins', {})
        if username in admins:
            user_data = admins[username]
            if self.verify_password(password, user_data.get('password', '')):
                return True, 'admin'

        # Check regular users
        users = self.config.get('users', {})
        if username in users:
            user_data = users[username]
            if self.verify_password(password, user_data.get('password', '')):
                return True, 'user'

        return False, None

    def clear_failed_attempts(self, username, ip_address):
        """Clear failed attempts for successful login"""
        key = f"{username}:{ip_address}"
        if key in self.failed_attempts:
            del self.failed_attempts[key]

    def get_security_stats(self):
        """Get security statistics"""
        locked_ips = self.load_locked_ips()
        active_locks = [lock for lock in locked_ips
                        if time.time() < lock.get('time_locked', 0) + self.lockout_time]

        # Count whitelisted vs non-whitelisted events
        whitelisted_events = sum(1 for event in self.security_logs if event.get('ip_whitelisted', False))

        return {
            'total_events': len(self.security_logs),
            'whitelisted_events': whitelisted_events,
            'active_ip_locks': len(active_locks),
            'failed_attempts': len(self.failed_attempts),
            'recent_events': self.security_logs[-10:] if self.security_logs else [],
            'locked_ips': active_locks,
            'whitelist_info': {
                'enabled': self.enable_ip_whitelist,
                'entries': len(self.ip_whitelist),
                'whitelist': self.ip_whitelist_raw
            },
            'config': {
                'max_attempts': self.max_attempts,
                'lockout_time': self.lockout_time,
                'captcha_threshold': self.captcha_threshold,
                'session_timeout': self.session_timeout
            }
        }

    def update_auth_config(self, new_config):
        """Update authentication configuration and reload whitelist"""
        self.config.update(new_config)
        if self.save_config(self.config):
            # Reload settings
            self.max_attempts = self.config.get('auth_max_attempts', 5)
            self.lockout_time = self.config.get('auth_lockout_time', 300)
            self.captcha_threshold = self.config.get('auth_captcha_threshold', 3)
            self.base_delay = self.config.get('auth_base_delay', 2000)
            self.session_timeout = self.config.get('auth_session_timeout', 7200)

            # Reload IP whitelist settings
            security_settings = self.config.get('security_settings', {}).get('rate_limiting', {})
            old_whitelist_enabled = self.enable_ip_whitelist
            self.enable_ip_whitelist = security_settings.get('enable_ip_whitelist', False)
            self.ip_whitelist_raw = security_settings.get('ip_whitelist', [])
            self.ip_whitelist = self.parse_ip_whitelist(self.ip_whitelist_raw)

            # Log whitelist changes
            if old_whitelist_enabled != self.enable_ip_whitelist:
                status = "enabled" if self.enable_ip_whitelist else "disabled"
                logger.info(f"IP whitelist {status} via configuration update")

            if self.enable_ip_whitelist:
                logger.info(f"IP whitelist updated with {len(self.ip_whitelist)} entries")

            return True
        return False

    def add_user(self, username, password, role='user'):
        """Add a new user"""
        hashed_password = self.hash_password(password)
        user_data = {
            'password': hashed_password,
            'role': role,
            'created': datetime.now().isoformat()
        }

        if role == 'admin':
            if 'admins' not in self.config:
                self.config['admins'] = {}
            self.config['admins'][username] = user_data
        else:
            if 'users' not in self.config:
                self.config['users'] = {}
            self.config['users'][username] = user_data

        return self.save_config(self.config)

    def remove_user(self, username):
        """Remove a user"""
        removed = False

        if 'admins' in self.config and username in self.config['admins']:
            del self.config['admins'][username]
            removed = True

        if 'users' in self.config and username in self.config['users']:
            del self.config['users'][username]
            removed = True

        if removed:
            return self.save_config(self.config)
        return False


# Global auth manager instance
auth_manager = AuthManager()


def requires_auth(f):
    """Decorator to require authentication for routes"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated
        if 'authenticated' not in session or not session['authenticated']:
            # Log unauthorized access attempt with whitelist info
            auth_manager.log_security_event('unauthorized_access',
                                            f'Attempted to access {request.endpoint}',
                                            request.remote_addr)

            # Store the original URL they were trying to access
            if request.method == 'GET':
                session['next_url'] = request.url

            # Handle API requests differently
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required', 'redirect': '/login'}), 401

            # Redirect to login page
            return redirect(url_for('login'))

        return f(*args, **kwargs)

    return decorated_function


def requires_admin(f):
    """Decorator to require admin role"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)

    return decorated_function