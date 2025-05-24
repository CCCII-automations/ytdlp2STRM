from datetime import datetime
import argparse
from clases.log import Logger, LogLevel
import config.plugins as plugins
from sanitize_filename import sanitize
import sys
import os
import traceback

# Initialize logger with appropriate settings
logger = Logger(
    log_file='logs/cli.log',
    min_level=LogLevel.DEBUG,
    enable_colors=True
)


def main(raw_args=None):
    """Main CLI entry point with enhanced logging"""
    start_time = datetime.now()

    # Log CLI startup
    logger.info("CLI", f"Starting CLI v1.0.1 - PID: {os.getpid()}")
    logger.debug("CLI", "Raw arguments", {"args": raw_args or sys.argv[1:]})

    parser = argparse.ArgumentParser(
        description='YTDLP2STRM - Convert YouTube content to STRM files',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('-m', '--media', help='Media platform (e.g., youtube, twitch)')
    parser.add_argument('-p', '--params', help='Comma-separated params for media platform')
    parser.add_argument('-v', '--version', action='store_true', help='Show YTDLP2STRM version')
    # Keep working for old version
    parser.add_argument('--m', dest='old_media', help='Media platform (deprecated)')
    parser.add_argument('--p', dest='old_params', help='Params to media platform mode (deprecated)')

    try:
        args = parser.parse_args(raw_args)
        logger.debug("CLI", "Parsed arguments", {
            "media": args.media,
            "params": args.params,
            "version": args.version,
            "old_media": args.old_media,
            "old_params": args.old_params
        })
    except SystemExit as e:
        logger.error("CLI", f"Argument parsing failed with exit code: {e.code}")
        raise
    except Exception as e:
        logger.critical("CLI", f"Unexpected error parsing arguments: {str(e)}",
                        {"traceback": traceback.format_exc()})
        raise

    # Determine method and params with backward compatibility
    method = args.media if args.media else args.old_media
    params = args.params if args.params else args.old_params

    if args.old_media or args.old_params:
        logger.warning("CLI", "Using deprecated argument format (--m/--p). Please use -m/-p instead.")

    # Parse params
    if params:
        params = params.split(',')
        logger.debug("CLI", f"Split params into list", {"params": params})
    else:
        params = None
        logger.debug("CLI", "No params provided")

    # Handle version flag
    if args.version:
        version = '1.0.1'
        logger.info("CLI", f"YTDLP2STRM version: {version}")
        logger.ui(f"YTDLP2STRM version: {version}")
        return

    # Validate method
    if not method:
        logger.error("CLI", "No media platform specified. Use -m/--media to specify platform.")
        parser.print_help()
        return

    # Plugin name normalization
    original_method = method
    try:
        if "plugins." in method:
            method = method.split('.')[1]
            logger.debug("CLI", f"Stripped 'plugins.' prefix from method",
                         {"original": original_method, "normalized": method})

        # Legacy compatibility
        if method == "make_files_strm":
            logger.info("CLI", "Converting legacy 'make_files_strm' to 'youtube'")
            method = "youtube"
    except Exception as e:
        logger.error("CLI", f"Error normalizing method name: {str(e)}",
                     {"method": original_method})
        method = None

    # Legacy param compatibility for specific platforms
    if params:
        try:
            # Twitch compatibility
            if len(params) > 1 and params[0] == "twitch":
                logger.info("CLI", "Applying Twitch legacy param conversion",
                            {"original": params, "converted": [params[1]]})
                params = [params[1]]

            # Redirect/stream compatibility
            if 'redirect' in params:
                logger.info("CLI", "Converting 'redirect' param to 'direct'")
                params = ["direct"]
            elif 'stream' in params:
                logger.info("CLI", "Converting 'stream' param to 'bridge'")
                params = ["bridge"]
        except Exception as e:
            logger.error("CLI", f"Error processing legacy params: {str(e)}",
                         {"params": params})
            params = None

    # Log execution details
    dt_string = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    logger.info("CLI", f"Executing method '{method}' with params {params} at {dt_string}")

    # Check if plugin exists
    plugin_path = f"plugins.{method}.to_strm"
    try:
        # Verify plugin exists before eval
        parts = plugin_path.split('.')
        module = plugins
        for part in parts[1:-1]:
            module = getattr(module, part)
        if not hasattr(module, parts[-1]):
            logger.error("CLI", f"Plugin method '{plugin_path}' not found")
            return False
    except AttributeError as e:
        logger.error("CLI", f"Plugin '{method}' not found", {"error": str(e)})
        return False

    # Execute plugin
    result = False
    try:
        if params is not None:
            logger.info("CLI", f"Calling {plugin_path} with params", {"params": params})
            result = eval(f"{plugin_path}")(*params)
        else:
            logger.info("CLI", f"Calling {plugin_path} without params")
            result = eval(f"{plugin_path}")()

        # Log execution result
        elapsed = (datetime.now() - start_time).total_seconds()
        if result:
            logger.info("CLI", f"Plugin execution completed successfully in {elapsed:.2f}s")
        else:
            logger.warning("CLI", f"Plugin execution completed with warnings/errors in {elapsed:.2f}s")

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.critical("CLI", f"Plugin execution failed after {elapsed:.2f}s",
                        {"error": str(e), "traceback": traceback.format_exc()})
        raise

    return result


if __name__ == "__main__":
    try:
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)

        # Run main with system arguments
        result = main()

        # Exit with appropriate code
        sys.exit(0 if result is not False else 1)

    except KeyboardInterrupt:
        logger.warning("CLI", "Process interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.critical("CLI", f"Unhandled exception: {str(e)}")
        sys.exit(1)