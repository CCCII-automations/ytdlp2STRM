# =============================================================================
# UPDATED config/routes.py - Fixed Secret Key Setup
# =============================================================================

import logging
import json
import os
import secrets
from datetime import timedelta

logger = logging.getLogger(__name__)


def ensure_secret_key(app):
    """Ensure Flask app has a secret key set BEFORE any routes are registered"""

    if app.secret_key:
        logger.info(f"✓ Secret key already set (length: {len(app.secret_key)})")
        return True

    # Try to load from config file
    config_file = './config/config.json'
    secret_key = None

    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
                secret_key = config.get('app_secret_key')

            if secret_key:
                app.secret_key = secret_key
                logger.info("✓ Secret key loaded from config.json")
                return True
        else:
            logger.warning("Config file not found")

    except Exception as e:
        logger.error(f"Failed to load secret key from config: {e}")

    # Generate and save a new secret key
    try:
        new_secret_key = secrets.token_hex(32)
        app.secret_key = new_secret_key

        # Save to config file
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
            except:
                config = {}
        else:
            config = {
                "ytdlp2strm_host": "0.0.0.0",
                "ytdlp2strm_port": 5000,
                "ytdlp2strm_keep_old_strm": "True",
                "ytdlp2strm_temp_file_duration": 86400,
                "cookies": "none",
                "cookie_value": "",
                "log_level": "INFO",
                "auth_max_attempts": 5,
                "auth_lockout_time": 300,
                "auth_captcha_threshold": 3,
                "auth_base_delay": 2000,
                "auth_session_timeout": 7200,
                "auth_enable_captcha": True,
                "auth_log_events": True,
                "admins": {
                    "admin": {
                        "password": "password123",
                        "role": "admin",
                        "created": "2024-12-19T12:00:00.000Z",
                        "description": "Default administrator"
                    }
                },
                "users": {
                    "user": {
                        "password": "userpass",
                        "role": "user",
                        "created": "2024-12-19T12:00:00.000Z",
                        "description": "Default user"
                    }
                }
            }

        config['app_secret_key'] = new_secret_key

        # Ensure config directory exists
        os.makedirs(os.path.dirname(config_file), exist_ok=True)

        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)

        logger.info("✓ Generated new secret key and saved to config.json")
        logger.warning("⚠ New secret key generated - existing sessions will be invalidated")
        return True

    except Exception as e:
        logger.error(f"Failed to generate/save secret key: {e}")
        # Last resort - set temporary key
        app.secret_key = 'temporary-secret-key-not-secure'
        logger.error("⚠ Using temporary insecure secret key!")
        return False


def register_all_routes(app):
    """Register all plugin routes with the Flask app and configure authentication"""

    # =============================================================================
    # CRITICAL: ENSURE SECRET KEY IS SET FIRST
    # =============================================================================

    logger.info("=" * 60)
    logger.info("CONFIGURING FLASK APPLICATION SECURITY")
    logger.info("=" * 60)

    # Ensure secret key is set before doing anything else
    if not ensure_secret_key(app):
        logger.error("⚠ Failed to set secure secret key - authentication may not work properly")

    # =============================================================================
    # AUTHENTICATION CONFIGURATION
    # =============================================================================

    try:
        # Load configuration for session settings
        config_file = './config/config.json'
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
        else:
            config = {"auth_session_timeout": 7200}  # Default 2 hours

        # Configure session settings
        session_timeout = config.get('auth_session_timeout', 7200)
        app.permanent_session_lifetime = timedelta(seconds=session_timeout)

        # Configure session cookie settings for security
        app.config.update(
            SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax',
            PERMANENT_SESSION_LIFETIME=timedelta(seconds=session_timeout)
        )

        logger.info(f"✓ Session configuration applied:")
        logger.info(f"  Session timeout: {session_timeout} seconds")
        logger.info(f"  Cookie secure: {app.config['SESSION_COOKIE_SECURE']}")
        logger.info(f"  Cookie HTTP-only: {app.config['SESSION_COOKIE_HTTPONLY']}")
        logger.info(f"  Cookie SameSite: {app.config['SESSION_COOKIE_SAMESITE']}")

    except Exception as e:
        logger.error(f"Failed to configure session settings: {e}")
        # Set minimal safe defaults
        app.permanent_session_lifetime = timedelta(hours=2)
        app.config.update(
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax'
        )
        logger.warning("⚠ Using default session configuration")

    # =============================================================================
    # REGISTER UI ROUTES WITH AUTHENTICATION
    # =============================================================================

    # Import UI routes (includes authentication)
    try:
        logger.info("Importing UI routes with authentication...")
        import ui.routes
        logger.info("✓ UI routes imported successfully")

        # Try to get authentication statistics
        try:
            from ui.auth import auth_manager
            logger.info("✓ Authentication system initialized")

            # Log configuration info
            max_attempts = getattr(auth_manager, 'max_attempts', 'Unknown')
            lockout_time = getattr(auth_manager, 'lockout_time', 'Unknown')
            captcha_threshold = getattr(auth_manager, 'captcha_threshold', 'Unknown')

            logger.info(f"  Max login attempts: {max_attempts}")
            logger.info(f"  Lockout time: {lockout_time} seconds")
            logger.info(f"  CAPTCHA threshold: {captcha_threshold}")

        except ImportError as e:
            logger.error(f"Authentication system not available: {e}")
        except Exception as e:
            logger.error(f"Error checking authentication system: {e}")

    except ImportError as e:
        logger.error(f"Failed to import ui.routes: {e}")
        logger.error("⚠ Web interface will not be available!")

        # Create emergency route
        @app.route('/')
        def emergency_home():
            return f"""
            <h1>ytdlp2STRM - Setup Required</h1>
            <p>The authentication system could not be loaded.</p>
            <p>Error: {str(e)}</p>
            <p>Please check your setup and ensure all files are in place.</p>
            <hr>
            <p><a href="/debug/config">Debug Configuration</a></p>
            """

    # =============================================================================
    # REGISTER PLUGIN ROUTES
    # =============================================================================

    logger.info("Registering plugin routes...")

    # Import and register YouTube routes
    try:
        from plugins.youtube.routes import youtube_bp
        app.register_blueprint(youtube_bp)
        logger.info("✓ YouTube routes registered")
    except ImportError as e:
        logger.error(f"Failed to import YouTube routes: {e}")
    except AttributeError as e:
        logger.error(f"YouTube routes missing blueprint: {e}")

    # Import and register Twitch routes
    try:
        from plugins.twitch.routes import twitch_bp
        app.register_blueprint(twitch_bp)
        logger.info("✓ Twitch routes registered")
    except ImportError as e:
        logger.error(f"Failed to import Twitch routes: {e}")
    except AttributeError as e:
        logger.error(f"Twitch routes missing blueprint: {e}")

    # Import and register Crunchyroll routes
    try:
        from plugins.crunchyroll.routes import crunchyroll_bp
        app.register_blueprint(crunchyroll_bp)
        logger.info("✓ Crunchyroll routes registered")
    except ImportError as e:
        logger.error(f"Failed to import Crunchyroll routes: {e}")
    except AttributeError as e:
        logger.error(f"Crunchyroll routes missing blueprint: {e}")

    # Import and register Pokemon TV routes
    try:
        from plugins.pokemon_tv.routes import pokemon_tv_bp
        app.register_blueprint(pokemon_tv_bp)
        logger.info("✓ Pokemon TV routes registered")
    except ImportError as e:
        logger.error(f"Failed to import Pokemon TV routes: {e}")
    except AttributeError as e:
        logger.error(f"Pokemon TV routes missing blueprint: {e}")

    # Import and register Telegram routes
    try:
        from plugins.telegram.routes import telegram_bp
        app.register_blueprint(telegram_bp)
        logger.info("✓ Telegram routes registered")
    except ImportError as e:
        logger.error(f"Failed to import Telegram routes: {e}")
    except AttributeError as e:
        logger.error(f"Telegram routes missing blueprint: {e}")

    # =============================================================================
    # FINAL SETUP AND VALIDATION
    # =============================================================================

    logger.info("=" * 60)
    logger.info("ROUTE REGISTRATION COMPLETED")
    logger.info("=" * 60)

    # Count and categorize routes
    total_routes = 0
    protected_routes = 0
    public_routes = 0

    logger.info("Registered Flask routes:")
    for rule in app.url_map.iter_rules():
        total_routes += 1
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))

        # Determine if route is likely protected
        public_endpoints = ['login', 'generate_captcha', 'static', 'emergency_home']
        is_public = rule.endpoint in public_endpoints or rule.endpoint.startswith('static')

        if is_public:
            public_routes += 1
            status = "🔓"
        else:
            protected_routes += 1
            status = "🔒"

        logger.info(f"  {status} {rule.endpoint:30s} {methods:10s} {rule.rule}")

    # Summary
    logger.info("=" * 60)
    logger.info("REGISTRATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"✓ Total routes registered: {total_routes}")
    logger.info(f"✓ Protected routes: {protected_routes}")
    logger.info(f"✓ Public routes: {public_routes}")
    logger.info(f"✓ Secret key configured: {'Yes' if app.secret_key and len(app.secret_key) > 20 else 'No'}")
    logger.info(f"✓ Session timeout: {app.permanent_session_lifetime}")

    if app.secret_key and len(app.secret_key) > 20:
        logger.info("🔐 Authentication system is ready!")
        logger.info("   Access your application and you'll be redirected to login")
    else:
        logger.error("⚠ Secret key not properly configured - authentication will not work!")

    logger.info("=" * 60)


# Legacy imports for backwards compatibility
try:
    import ui.routes
    import plugins.youtube.routes
    import plugins.twitch.routes
    import plugins.crunchyroll.routes
    import plugins.pokemon_tv.routes
    import plugins.telegram.routes
except ImportError:
    pass  # Handled in the function above