import logging

logger = logging.getLogger(__name__)


def register_all_routes(app):
    """Register all plugin routes with the Flask app"""

    # Import UI routes (if they need registration)
    try:
        import ui.routes
        logger.info("✓ Imported ui.routes")
        # If ui.routes has a blueprint, register it here:
        # from ui.routes import ui_bp
        # app.register_blueprint(ui_bp)
    except ImportError as e:
        logger.error(f"Failed to import ui.routes: {e}")

    # Import and register YouTube routes
    try:
        from plugins.youtube.routes import youtube_bp
        app.register_blueprint(youtube_bp)
        logger.info("✓ Imported and registered YouTube routes")
    except ImportError as e:
        logger.error(f"Failed to import YouTube routes: {e}")
    except AttributeError as e:
        logger.error(f"YouTube routes missing blueprint: {e}")

    # Import and register Twitch routes
    try:
        from plugins.twitch.routes import twitch_bp  # Adjust blueprint name as needed
        app.register_blueprint(twitch_bp)
        logger.info("✓ Imported and registered Twitch routes")
    except ImportError as e:
        logger.error(f"Failed to import Twitch routes: {e}")
    except AttributeError as e:
        logger.error(f"Twitch routes missing blueprint: {e}")

    # Import and register Crunchyroll routes
    try:
        from plugins.crunchyroll.routes import crunchyroll_bp  # Adjust blueprint name as needed
        app.register_blueprint(crunchyroll_bp)
        logger.info("✓ Imported and registered Crunchyroll routes")
    except ImportError as e:
        logger.error(f"Failed to import Crunchyroll routes: {e}")
    except AttributeError as e:
        logger.error(f"Crunchyroll routes missing blueprint: {e}")

    # Import and register Pokemon TV routes
    try:
        from plugins.pokemon_tv.routes import pokemon_tv_bp  # Adjust blueprint name as needed
        app.register_blueprint(pokemon_tv_bp)
        logger.info("✓ Imported and registered Pokemon TV routes")
    except ImportError as e:
        logger.error(f"Failed to import Pokemon TV routes: {e}")
    except AttributeError as e:
        logger.error(f"Pokemon TV routes missing blueprint: {e}")

    # Import and register Telegram routes
    try:
        from plugins.telegram.routes import telegram_bp  # Adjust blueprint name as needed
        app.register_blueprint(telegram_bp)
        logger.info("✓ Imported and registered Telegram routes")
    except ImportError as e:
        logger.error(f"Failed to import Telegram routes: {e}")
    except AttributeError as e:
        logger.error(f"Telegram routes missing blueprint: {e}")

    logger.info("All plugin routes registration completed")


# Legacy imports for backwards compatibility (if needed)
try:
    import ui.routes
    import plugins.youtube.routes
    import plugins.twitch.routes
    import plugins.crunchyroll.routes
    import plugins.pokemon_tv.routes
    import plugins.telegram.routes
except ImportError:
    pass  # Handled in the function above