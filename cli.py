from datetime import datetime
import argparse
import config.plugins as plugins
from clases.log import log as l
from sanitize_filename import sanitize


def main(*raw_args):
    parser = argparse.ArgumentParser()

    parser.add_argument('-m', '--media', help='Media platform')
    parser.add_argument('-p', '--params', help='Params to media platform mode.')
    parser.add_argument('-v', '--version', help='Show YTDLP2STRM version')
    # Keep working for old version
    parser.add_argument('--m', help='Media platform (old)')
    parser.add_argument('--p', help='Params to media platform mode (old)')
    # --

    args = parser.parse_args(raw_args)
    method = args.media if args.media is not None else "error"
    params = args.params.split(',') if args.params is not None else None

    # Backward compatibility
    if method == "error":
        method = args.m if args.m is not None else None
    if params is None:
        params = args.p.split(',') if args.p is not None else None

    try:
        if "plugins" in method:
            method = method.split('.')[1]
        if method == "make_files_strm":
            method = "youtube"
    except:
        method = None

    try:
        if "twitch" in params:
            params = [params[1]]
        if 'redirect' in params:
            params = ["direct"]
        if 'stream' in params:
            params = ["bridge"]
    except:
        params = None

    now = datetime.now()
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")

    log_text = "Running {} with {} params".format(method, params)
    l.log("CLI", log_text)

    if args.version:
        log_text = 'ytdlp2STRM version: {}'.format('1.0.1')
        l.log("CLI", log_text)

    if params is not None:
        eval("{}.{}.{}".format("plugins", method, "to_strm"))(*params)


if __name__ == "__main__":
    main()
