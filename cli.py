from datetime import datetime
import argparse
import sys
import config.plugins as plugins
from clases.log import log as l
from sanitize_filename import sanitize


def main(*raw_args):
    # Debug: Print all received arguments
    l.log("CLI", f"Received raw_args: {raw_args}")
    l.log("CLI", f"sys.argv: {sys.argv}")

    parser = argparse.ArgumentParser()

    parser.add_argument('-m', '--media', help='Media platform')
    parser.add_argument('-p', '--params', help='Params to media platform mode.')
    parser.add_argument('-v', '--version', help='Show YTDLP2STRM version')
    # Keep working for old version
    parser.add_argument('--m', help='Media platform (old)')
    parser.add_argument('--p', help='Params to media platform mode (old)')

    # Parse arguments
    if raw_args:
        args = parser.parse_args(raw_args)
    else:
        args = parser.parse_args()

    # Debug: Print parsed arguments
    l.log("CLI", f"Parsed args: media={args.media}, params={args.params}")

    method = args.media if args.media is not None else "error"
    params = args.params.split(',') if args.params is not None else None

    # Backward compatibility
    if method == "error":
        method = args.m if args.m is not None else None
    if params is None:
        params = args.p.split(',') if args.p is not None else None

    # Debug: Print processed values
    l.log("CLI", f"Processed: method={method}, params={params}")

    try:
        if method and "plugins" in method:
            method = method.split('.')[1]
        if method == "make_files_strm":
            method = "youtube"
    except:
        method = None

    try:
        if params:
            if "twitch" in params:
                params = [params[1]]
            if 'redirect' in params:
                params = ["direct"]
            if 'stream' in params:
                params = ["bridge"]
            if 'download' in params:
                params = ["download"]
    except Exception as e:
        l.log("CLI", f"Error processing params: {e}")
        params = None

    now = datetime.now()
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")

    log_text = "Running {} with {} params".format(method, params)
    l.log("CLI", log_text)

    if args.version:
        log_text = 'ytdlp2STRM version: {}'.format('1.0.1')
        l.log("CLI", log_text)

    # Enhanced execution logic
    if method is None:
        l.log("CLI", "ERROR: No method specified")
        return

    if params is not None:
        if method == "youtube":
            if params and "download" in params:
                l.log("CLI", f"Calling YouTube download mode with params: {params}")
                try:
                    eval("{}.{}.{}".format("plugins", method, "to_download"))(*params)
                except Exception as e:
                    l.log("CLI", f"Error calling to_download: {e}")
            else:
                l.log("CLI", f"Calling YouTube STRM mode with params: {params}")
                try:
                    eval("{}.{}.{}".format("plugins", method, "to_strm"))(*params)
                except Exception as e:
                    l.log("CLI", f"Error calling to_strm: {e}")
        else:
            l.log("CLI", f"Calling {method} plugin with params: {params}")
            try:
                eval("{}.{}.{}".format("plugins", method, "to_strm"))(*params)
            except Exception as e:
                l.log("CLI", f"Error calling plugin: {e}")
    else:
        # Handle case when no params provided
        if method == "youtube":
            l.log("CLI", "No params provided, using default STRM mode")
            try:
                eval("{}.{}.{}".format("plugins", method, "to_strm"))("direct")
            except Exception as e:
                l.log("CLI", f"Error calling default mode: {e}")
        elif method is not None:
            l.log("CLI", f"No params provided for {method}, using default")
            try:
                eval("{}.{}.{}".format("plugins", method, "to_strm"))("direct")
            except Exception as e:
                l.log("CLI", f"Error calling default for {method}: {e}")


if __name__ == "__main__":
    main()