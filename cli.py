from datetime import datetime
import argparse
import sys
import os
import traceback

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import config.plugins as plugins
    from clases.log import log as l
    from sanitize_filename import sanitize
except ImportError as e:
    print(f"Import error: {e}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    sys.exit(1)


def main(*raw_args):
    """Main CLI entry point"""
    # Debug: Print all received arguments
    print(f"[CLI] Starting with args: {raw_args if raw_args else sys.argv[1:]}")
    l.log("CLI", f"Received raw_args: {raw_args}")
    l.log("CLI", f"sys.argv: {sys.argv}")

    parser = argparse.ArgumentParser(
        prog='ytdlp2STRM CLI',
        description='YouTube/Twitch to STRM converter CLI'
    )

    parser.add_argument('-m', '--media', help='Media platform (e.g., youtube, twitch)')
    parser.add_argument('-p', '--params', help='Parameters for media platform mode')
    parser.add_argument('-v', '--version', action='store_true', help='Show YTDLP2STRM version')

    # Keep backward compatibility
    parser.add_argument('--m', dest='old_media', help='Media platform (old format)')
    parser.add_argument('--p', dest='old_params', help='Parameters (old format)')

    # Parse arguments
    try:
        if raw_args:
            args = parser.parse_args(raw_args)
        else:
            args = parser.parse_args()
    except SystemExit:
        print("[CLI] Error parsing arguments")
        return

    # Debug: Print parsed arguments
    print(f"[CLI] Parsed args: media={args.media}, params={args.params}")
    l.log("CLI", f"Parsed args: media={args.media}, params={args.params}")

    # Get method and params with backward compatibility
    method = args.media or args.old_media
    params = args.params or args.old_params

    # Handle version flag
    if args.version:
        version = '1.0.1'
        print(f'ytdlp2STRM version: {version}')
        l.log("CLI", f'ytdlp2STRM version: {version}')
        return

    # Validate method
    if not method:
        print("[CLI] ERROR: No media platform specified. Use --media <platform>")
        l.log("CLI", "ERROR: No method specified")
        return

    # Process params
    if params:
        params_list = [p.strip() for p in params.split(',')]
    else:
        params_list = None

    # Log execution
    now = datetime.now()
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    log_text = f"[{dt_string}] Running {method} with params: {params_list}"
    print(log_text)
    l.log("CLI", log_text)

    # Execute the appropriate plugin method
    try:
        if method == "youtube":
            print(f"[CLI] Loading YouTube plugin...")
            l.log("CLI", f"Loading YouTube plugin...")

            # FIXED: Import the module, not just the function
            from plugins.youtube import youtube as youtube_module

            if params and params in ["download", "download-all"]:
                print(f"[CLI] Executing YouTube download mode")
                l.log("CLI", f"Calling YouTube download mode")
                # FIXED: Call the function from the module
                youtube_module.to_download('download')
            else:
                # Default to STRM mode
                print(f"[CLI] Executing YouTube STRM mode with params: {params or 'direct'}")
                l.log("CLI", f"Calling YouTube STRM mode with params: {params or 'direct'}")
                # FIXED: Call the function from the module
                youtube_module.to_strm(params or 'direct')

        elif method == "twitch":
            print(f"[CLI] Loading Twitch plugin...")
            l.log("CLI", f"Loading Twitch plugin...")

            # Import Twitch module
            from plugins.twitch import twitch as twitch_module

            print(f"[CLI] Executing Twitch with params: {params or 'direct'}")
            twitch_module.to_strm(params or 'direct')

        else:
            # Try to dynamically load the plugin
            print(f"[CLI] Attempting to load plugin: {method}")
            l.log("CLI", f"Attempting to load plugin: {method}")

            try:
                # Dynamic import - FIXED: Import the module correctly
                plugin_module = __import__(f'plugins.{method}.{method}', fromlist=[method])

                if hasattr(plugin_module, 'to_strm'):
                    print(f"[CLI] Executing {method} plugin")
                    plugin_module.to_strm(params or 'direct')
                else:
                    print(f"[CLI] ERROR: Plugin {method} does not have to_strm method")
                    l.log("CLI", f"ERROR: Plugin {method} missing to_strm method")

            except ImportError as e:
                print(f"[CLI] ERROR: Failed to import plugin {method}: {e}")
                l.log("CLI", f"ERROR: Failed to import plugin {method}: {e}")

    except Exception as e:
        error_msg = f"ERROR executing {method}: {str(e)}"
        print(f"[CLI] {error_msg}")
        l.log("CLI", error_msg)

        # Print full traceback for debugging
        traceback.print_exc()
        l.log("CLI", f"Full traceback: {traceback.format_exc()}")

    print(f"[CLI] Execution completed")
    l.log("CLI", "Execution completed")


if __name__ == "__main__":
    # Ensure output is unbuffered
    sys.stdout.flush()
    main()