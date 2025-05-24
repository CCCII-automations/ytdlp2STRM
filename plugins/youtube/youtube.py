import os
import json
import time
import platform
import subprocess
import requests
import html
import re
import threading
from datetime import datetime
from cachetools import TTLCache
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any

# Try to import dependencies, with fallbacks for standalone mode
try:
    from clases.config import config as c
    from clases.worker import worker as w
    from clases.folders import folders as f
    from clases.nfo import nfo as n
    from clases.log import Logger, LogLevel
except ImportError as e:
    print(f"Warning: Could not import clases modules: {e}")
    if __name__ == "__main__":
        print("Some functionality may be limited in standalone mode.")


    # Create minimal fallbacks for both standalone and import mode
    class Logger:
        def __init__(self, *args, **kwargs):
            self.min_level = kwargs.get('min_level', 'INFO')

        def debug(self, author, msg, **kwargs):
            print(f"[DEBUG] {author}: {msg}")

        def info(self, author, msg, **kwargs):
            print(f"[INFO] {author}: {msg}")

        def warning(self, author, msg, **kwargs):
            print(f"[WARNING] {author}: {msg}")

        def error(self, author, msg, **kwargs):
            print(f"[ERROR] {author}: {msg}")


    class LogLevel:
        DEBUG = "DEBUG"
        INFO = "INFO"
        WARNING = "WARNING"
        ERROR = "ERROR"

try:
    from sanitize_filename import sanitize
except ImportError:
    # Fallback sanitize function
    def sanitize(filename):
        import re
        return re.sub(r'[<>:"/\\|?*]', '_', filename)

try:
    from flask import stream_with_context, Response, send_file, redirect, abort, request

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    if __name__ != "__main__":
        raise
from pathlib import Path
import pwd
import grp

# Caches
recent_requests = TTLCache(maxsize=500, ttl=60)
channel_cache = TTLCache(maxsize=100, ttl=3600)

# Thread lock
file_lock = threading.Lock()

# Load configs - with error handling for standalone mode
try:
    ytdlp2strm_cfg = c.config('./config/config.json').get_config()
    cfg = c.config('./plugins/youtube/config.json').get_config()
    channels = c.config(cfg["channels_list_file"]).get_channels()
except Exception as e:
    if __name__ == "__main__":
        # In standalone mode, use default values if config files don't exist
        print(f"Warning: Could not load configuration files: {e}")
        print("Using default configuration. Use --config to specify config file.")
        ytdlp2strm_cfg = {
            'ytdlp2strm_host': 'localhost',
            'ytdlp2strm_port': 5000
        }
        cfg = {
            "strm_output_folder": "./strm_files",
            "days_dateafter": "30",
            "videos_limit": 50,
            "cookies": "cookies-from-browser",
            "cookie_value": "chromium",
            "proxy": False,
            "proxy_url": "",
            "max_workers": 4,
            "request_timeout": 30,
            "log_level": "INFO",
            "sponsorblock": False,
            "sponsorblock_cats": "sponsor,intro,outro",
            "channels_list_file": "./channels.txt"
        }
        channels = []
    else:
        raise

media_folder = cfg["strm_output_folder"]
days_dateafter = cfg["days_dateafter"]
videos_limit = cfg["videos_limit"]
cookies = cfg.get("cookies", "cookies-from-browser")
cookie_value = cfg.get("cookie_value", "chromium")
proxy = cfg.get("proxy", False)
proxy_url = cfg.get("proxy_url", "")
MAX_WORKERS = cfg.get("max_workers", 4)
REQUEST_TIMEOUT = cfg.get("request_timeout", 30)

# Configure logging
LOG_LEVEL_MAP = {'DEBUG': LogLevel.DEBUG, 'INFO': LogLevel.INFO, 'WARNING': LogLevel.WARNING, 'ERROR': LogLevel.ERROR}
LOG_LEVEL = LOG_LEVEL_MAP.get(cfg.get("log_level", "INFO"), LogLevel.INFO)

# Initialize logger
logger = Logger(log_file='youtube.log', max_days=7, enable_colors=True, min_level=LOG_LEVEL)

source_platform = "youtube"
host = ytdlp2strm_cfg['ytdlp2strm_host']
port = ytdlp2strm_cfg['ytdlp2strm_port']
if os.environ.get('AM_I_IN_A_DOCKER_CONTAINER'):
    port = os.environ.get('DOCKER_PORT', port)

Path(media_folder).mkdir(parents=True, exist_ok=True)

# Handle permissions safely for standalone mode
try:
    # Get UID and GID of the current user
    uid = os.getuid()
    gid = os.getgid()
    os.chown(media_folder, uid, gid)
    os.chmod(media_folder, 0o2775)
except (AttributeError, OSError, PermissionError) as e:
    # os.getuid() doesn't exist on Windows, or permission denied
    if __name__ == "__main__":
        print(f"Warning: Could not set folder permissions: {e}")
    else:
        logger.warning("SETUP", f"Could not set folder permissions: {e}")


class YtDlpCommandBuilder:
    """Centralized yt-dlp command builder"""

    def __init__(self):
        self.base_args = [
            'yt-dlp',
            '-t', 'sleep',
            '--no-warnings'
        ]
        self._add_cookies()
        self._add_proxy()

    def _add_cookies(self):
        """Add cookie configuration to base args"""
        self.base_args.extend([f'--{cookies}', cookie_value])

    def _add_proxy(self):
        """Add proxy configuration if enabled"""
        if proxy and proxy_url:
            self.base_args.extend(['--proxy', proxy_url])

    def build(self, *additional_args) -> List[str]:
        """Build command with additional arguments"""
        return self.base_args + list(additional_args)

    def build_info_extraction(self, url: str, **kwargs) -> List[str]:
        """Build command for info extraction (JSON dump)"""
        cmd = self.build('--dump-json')

        # Add playlist controls if specified
        if 'playlist_start' in kwargs:
            cmd.extend(['--playlist-start', str(kwargs['playlist_start'])])
        if 'playlist_end' in kwargs:
            cmd.extend(['--playlist-end', str(kwargs['playlist_end'])])

        # Add date filter if specified
        if 'dateafter' in kwargs:
            cmd.extend(['--dateafter', kwargs['dateafter']])

        # Add format if specified
        if 'format' in kwargs:
            cmd.extend(['-f', kwargs['format']])

        # Add compatibility options for channels
        if 'channel_compat' in kwargs and kwargs['channel_compat']:
            cmd.extend([
                '--compat-options', 'no-youtube-channel-redirect',
                '--compat-options', 'no-youtube-unavailable-videos'
            ])

        cmd.append(url)
        return cmd

    def build_url_extraction(self, url: str, format_selector: str = 'best') -> List[str]:
        """Build command for URL extraction"""
        return self.build('-f', format_selector, '--get-url', url)

    def build_metadata_extraction(self, url: str, print_template: str, **kwargs) -> List[str]:
        """Build command for metadata extraction"""
        cmd = self.build('--print', print_template)

        if 'playlist_items' in kwargs:
            cmd.extend(['--playlist-items', str(kwargs['playlist_items'])])
        if 'restrict_filenames' in kwargs and kwargs['restrict_filenames']:
            cmd.append('--restrict-filenames')
        if 'ignore_errors' in kwargs and kwargs['ignore_errors']:
            cmd.append('--ignore-errors')

        cmd.append(url)
        return cmd

    def build_thumbnail_list(self, url: str) -> List[str]:
        """Build command for listing thumbnails"""
        return self.build(
            '--list-thumbnails',
            '--restrict-filenames',
            '--ignore-errors',
            '--playlist-items', '0',
            url
        )

    def build_description_extraction(self, url: str, output_path: str) -> List[str]:
        """Build command for description extraction"""
        return self.build(
            '--write-description',
            '--playlist-items', '0',
            '--output', f'"{output_path}"',
            url
        )

    def build_download(self, url: str, **kwargs) -> List[str]:
        """Build command for downloading"""
        cmd = self.base_args.copy()  # Don't include --no-warnings for downloads

        if 'format' in kwargs:
            cmd.extend(['-f', kwargs['format']])
        if 'output' in kwargs:
            cmd.extend(['-o', kwargs['output']])
        if 'sponsorblock' in kwargs and kwargs['sponsorblock']:
            cmd.extend(['--sponsorblock-remove', kwargs.get('sponsorblock_cats', '')])

        # Add proxy and cookies
        cmd.extend([f'--{cookies}', cookie_value])
        if proxy and proxy_url:
            cmd.extend(['--proxy', proxy_url])

        cmd.append(url)
        return cmd

    def build_stream(self, url: str, **kwargs) -> List[str]:
        """Build command for streaming"""
        cmd = self.base_args.copy()
        cmd.extend(['-o', '-'])  # Output to stdout

        if 'format' in kwargs:
            cmd.extend(['-f', kwargs['format']])
        if 'sponsorblock' in kwargs and kwargs['sponsorblock']:
            cmd.extend(['--sponsorblock-remove', kwargs.get('sponsorblock_cats', '')])

        # Add proxy and cookies
        cmd.extend([f'--{cookies}', cookie_value])
        if proxy and proxy_url:
            cmd.extend(['--proxy', proxy_url])

        cmd.append(url)
        return cmd


# Global command builder instance
cmd_builder = YtDlpCommandBuilder()


class Youtube:
    def __init__(self, channel: str = None):
        self.channel = channel
        self.channel_url = None
        self.channel_name = None
        self.channel_description = None
        self.channel_poster = None
        self.channel_landscape = None

    def _exec(self, cmd: List[str], shell: bool = False, timeout: int = REQUEST_TIMEOUT) -> str:
        cmd_str = " ".join(cmd)
        logger.debug("YTDLP", f"Executing command: {cmd_str}")
        try:
            result = w.Worker(cmd).shell() if shell else w.Worker(cmd).output()
            logger.debug("YTDLP", f"Command output size: {len(result)} characters")
            return result
        except Exception as e:
            logger.error("YTDLP", f"Command failed: {cmd_str}", extra_data={"error": str(e)})
            return ""

    def get_results(self) -> List[Dict]:
        logger.info("YOUTUBE", f"Processing channel: {self.channel}")
        try:
            if 'extractaudio-' in self.channel:
                return self._handle_audio_extraction()
            if 'keyword' in self.channel:
                return self.get_keyword_videos()
            if 'list' in self.channel:
                return self._handle_playlist()
            return self._handle_regular_channel()
        except Exception as e:
            logger.error("YOUTUBE", f"get_results failed for channel: {self.channel}",
                         extra_data={"error": str(e)})
            return []

    def _handle_audio_extraction(self):
        is_list = 'list-' in self.channel
        url_key = self.channel.replace('extractaudio-', '')
        if is_list:
            url_key = url_key.replace('list-', '')
            self.channel_url = f'https://www.youtube.com/playlist?list={url_key}'
        else:
            self.channel_url = url_key if 'www.youtube' in url_key else f'https://www.youtube.com/{url_key}'
        self._populate_channel_info()
        self.channel_description = f'Playlist {self.channel_name}' if is_list else self.get_channel_description()
        return self.get_list_audios() if is_list else self.get_channel_audios()

    def _handle_playlist(self):
        url_key = self.channel.replace('list-', '')
        self.channel_url = f'https://www.youtube.com/playlist?list={url_key}'
        self._populate_channel_info()
        self.channel_description = f'Playlist {self.channel_name}'
        return self.get_list_videos()

    def _handle_regular_channel(self):
        raw = self.channel
        self.channel_url = raw if 'www.youtube' in raw else f'https://www.youtube.com/{raw}'
        self._populate_channel_info()
        return self.get_channel_videos()

    def _populate_channel_info(self):
        key = f"chan_{self.channel_url}"
        if key in channel_cache:
            info = channel_cache[key]
            self.channel_name = info['name']
            self.channel_poster = info['poster']
            self.channel_landscape = info['landscape']
            logger.debug("CACHE", f"Retrieved channel info from cache: {self.channel_name}")
        else:
            logger.debug("CACHE", f"Fetching fresh channel info for: {self.channel_url}")
            self.channel_name = self.get_channel_name()
            thumbs = self.get_channel_images()
            self.channel_poster = thumbs['poster']
            self.channel_landscape = thumbs['landscape']
            channel_cache[key] = {
                'name': self.channel_name,
                'poster': thumbs['poster'],
                'landscape': thumbs['landscape']
            }
            logger.debug("CACHE", f"Cached channel info: {self.channel_name}")

    def get_list_videos(self):
        cmd = cmd_builder.build_info_extraction(
            self.channel_url,
            playlist_start=1,
            playlist_end=videos_limit
        )
        logger.info("PLAYLIST", f"Fetching playlist videos from: {self.channel_url}")
        out = self._exec(cmd)
        return self._parse_results(out, playlist_id=self.channel_url.split('list=')[1])

    def get_keyword_videos(self):
        kw = self.channel.split('-')[1]
        url = f'ytsearch{videos_limit}:["{kw}"]'
        cmd_kwargs = {
            'format': 'best',
            'playlist_start': 1,
            'playlist_end': videos_limit
        }
        if days_dateafter != "0":
            cmd_kwargs['dateafter'] = f"today-{days_dateafter}days"

        cmd = cmd_builder.build_info_extraction(url, **cmd_kwargs)
        logger.info("SEARCH", f"Searching for keyword: {kw}")
        return self._parse_results(self._exec(cmd))

    def get_channel_videos(self):
        cu = self.channel_url + ('/videos' if '/streams' not in self.channel_url else '')
        cmd = cmd_builder.build_info_extraction(
            cu,
            dateafter=f"today-{days_dateafter}days",
            playlist_start=1,
            playlist_end=videos_limit
        )
        logger.info("CHANNEL", f"Fetching channel videos from: {cu}")
        return self._parse_results(self._exec(cmd))

    def get_channel_audios(self):
        cu = self.channel_url + ('/videos' if '/streams' not in self.channel_url else '')
        cmd = cmd_builder.build_info_extraction(
            cu,
            dateafter=f"today-{days_dateafter}days",
            playlist_start=1,
            playlist_end=videos_limit
        )
        logger.info("AUDIO", f"Fetching channel audios from: {cu}")
        return self._parse_results(self._exec(cmd), audio_mode=True)

    def get_list_audios(self):
        cmd = cmd_builder.build_info_extraction(
            self.channel_url,
            playlist_start=1,
            playlist_end=videos_limit
        )
        logger.info("AUDIO", f"Fetching playlist audios from: {self.channel_url}")
        return self._parse_results(self._exec(cmd), audio_mode=True,
                                   playlist_id=self.channel_url.split('list=')[1])

    def _parse_results(self, out: str, audio_mode: bool = False,
                       playlist_id: Optional[str] = None) -> List[Dict]:
        vids, lines = [], out.splitlines()
        non_empty_lines = [l for l in lines if l.strip()]
        logger.info("PARSER", f"Parsing {len(non_empty_lines)} video entries")

        for ln in lines:
            if not ln.strip():
                continue
            try:
                data = json.loads(ln)
                vid = data.get('id')
                if audio_mode:
                    vid += '-audio'
                vids.append({
                    'id': vid,
                    'title': data.get('title'),
                    'upload_date': data.get('upload_date'),
                    'thumbnail': data.get('thumbnail'),
                    'description': data.get('description', ''),
                    'channel_id': playlist_id or data.get('channel_id'),
                    'uploader_id': sanitize(self.channel_name) if playlist_id else data.get('uploader_id')
                })
            except json.JSONDecodeError:
                logger.warning("PARSER", f"JSON parse failed for line: {ln[:80]}")

        logger.info("PARSER", f"Successfully parsed {len(vids)} videos")
        return vids

    def get_channel_name(self) -> str:
        if 'playlist' in self.channel_url:
            fmt = '%(playlist_title)s'
        else:
            fmt = '%(channel)s'

        cmd = cmd_builder.build_metadata_extraction(
            self.channel_url,
            fmt,
            playlist_items=1,
            restrict_filenames=True,
            ignore_errors=True
        )
        logger.debug("METADATA", f"Fetching channel name for: {self.channel_url}")
        out = self._exec(cmd)
        name = sanitize(out.strip().strip('"'))
        logger.debug("METADATA", f"Channel name extracted: {name}")
        return name

    def get_channel_description(self) -> str:
        desc_file = f"{media_folder}/{sanitize(self.channel_name)}.description"

        if platform.system() == "Linux":
            cmd = cmd_builder.build_description_extraction(self.channel_url, desc_file)
            cmd.extend(['>', '/dev/null', '2>&1', '&&', 'cat', f'"{desc_file}"'])
        else:
            cmd = cmd_builder.build_description_extraction(self.channel_url, desc_file)
            cmd.extend(['>', 'nul', '2>&1', '&&', 'more', f'"{desc_file}"'])

        logger.debug("METADATA", f"Fetching channel description for: {self.channel_name}")
        out = self._exec(cmd, shell=True)
        if not out:
            try:
                with open(desc_file, 'r', encoding='utf-8') as rf:
                    out = rf.read()
                logger.debug("METADATA", "Read description from file")
            except Exception as e:
                out = f"Channel: {self.channel_name}"
                logger.warning("METADATA", f"Failed to read description file: {str(e)}")

        try:
            os.remove(desc_file)
        except:
            pass

        return out

    def get_channel_images(self) -> Dict[str, str]:
        cmd = cmd_builder.build_thumbnail_list(self.channel_url)
        logger.debug("THUMBNAILS", f"Fetching channel images for: {self.channel_url}")
        out = self._exec(cmd)
        lines = [' '.join(l.split()) for l in out.splitlines() if l.strip()]
        headers, thumbs = [], []

        for i, l in enumerate(lines):
            if '[' in l:
                continue
            parts = l.split(' ')
            if i == 0:
                headers = parts
            else:
                if parts[0] == 'ID':
                    continue
                try:
                    thumbs.append(dict(zip(headers, parts)))
                except Exception as e:
                    logger.warning("THUMBNAILS", f"Failed to parse thumbnail line: {l}")

        poster = next((t['URL'] for t in thumbs if t.get('ID') == 'avatar_uncropped'), '')
        banner = [t for t in thumbs if 'banner' in t.get('ID', '')]
        landscape = banner[-1]['URL'] if banner else ''

        logger.debug("THUMBNAILS", f"Found images - poster: {bool(poster)}, landscape: {bool(landscape)}")
        return {'poster': poster, 'landscape': landscape}


def filter_and_modify_bandwidth(m3u8: str) -> str:
    lines = m3u8.splitlines()
    best_bw, best_info, best_url = 0, None, None
    media_lines, sd_line = [], ""

    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF:"):
            try:
                bw = int(ln.split("BANDWIDTH=")[1].split(",")[0])
                url = lines[i + 1] if i + 1 < len(lines) else ""
                if bw > best_bw:
                    best_bw, best_info, best_url = bw, ln.replace(f"BANDWIDTH={bw}", "BANDWIDTH=279001"), url
            except Exception as e:
                logger.warning("M3U8", f"Stream parse failed for line: {ln}")
        elif ln.startswith("#EXT-X-MEDIA:URI"):
            if '234' in ln:
                media_lines.append(ln)
            else:
                sd_line = ln

    if sd_line and not any('234' in m for m in media_lines):
        media_lines.append(sd_line)

    out = "#EXTM3U\n#EXT-X-INDEPENDENT-SEGMENTS\n"
    for ml in media_lines:
        out += ml + "\n"
    if best_info and best_url:
        out += best_info + "\n" + best_url + "\n"

    logger.debug("M3U8", f"Filtered manifest - streams: {len(media_lines)}, bandwidth: {best_bw}")
    return out


def clean_text(txt: str) -> str:
    if not txt:
        return ""
    t = html.escape(txt)
    return re.sub(r'[^\w\s\[\]\(\)\-\_\'\"\/\.\:\;\,]', '', t)


def video_id_exists_in_content(folder: str, vid: str) -> bool:
    for r, d, files in os.walk(folder):
        for fn in files:
            if fn.endswith(".strm"):
                try:
                    with open(os.path.join(r, fn), 'r', encoding='utf-8') as f:
                        if vid in f.read():
                            return True
                except Exception as e:
                    logger.warning("FILE", f"Error reading file {fn}: {str(e)}")
    return False


def process_channel_videos(data):
    yt, videos, method = data
    if not videos:
        logger.info("PROCESS", f"No videos found for channel: {yt.channel_name}")
        return

    logger.info("PROCESS", f"Processing {len(videos)} videos for channel: {yt.channel_name}")
    chan_nfo, chan_folder = False, False
    proc_count = 0

    for vid in videos:
        try:
            vid_id = vid['id']
            cid = vid['channel_id']
            title = vid['title']
            thumb = vid['thumbnail']
            desc = vid['description']

            try:
                dt = datetime.strptime(vid['upload_date'], '%Y%m%d')
                up_date = dt.strftime('%Y-%m-%d')
                yr = dt.year
            except:
                up_date = datetime.now().strftime('%Y-%m-%d')
                yr = datetime.now().year

            uploader = vid['uploader_id']
            folder = f"{media_folder}/{sanitize(f'{uploader} [{cid}]')}"
            path = f"{folder}/{sanitize(title)}.strm"
            content = f"http://{host}:{port}/{source_platform}/{method}/{vid_id}"

            if video_id_exists_in_content(folder, vid_id):
                logger.debug("DUPLICATE", f"Video already exists: {vid_id}")
                continue

            with file_lock:
                if not chan_folder:
                    f.Folders().make_clean_folder(folder, False, ytdlp2strm_cfg)
                    chan_folder = True
                    logger.debug("FOLDER", f"Created channel folder: {folder}")

            if yt.channel_url:
                ch_land, ch_post, ch_desc = yt.channel_landscape, yt.channel_poster, yt.channel_description
            else:
                logger.debug("METADATA", f"Fetching metadata for channel: {cid}")
                tmp = Youtube(f'https://www.youtube.com/channel/{cid}')
                tmp._populate_channel_info()
                ch_land, ch_post, ch_desc = tmp.channel_landscape, tmp.channel_poster, tmp.get_channel_description()

            with file_lock:
                if not chan_nfo:
                    logger.debug("NFO", f"Creating channel NFO for: {uploader}")
                    n.nfo("tvshow", folder, {
                        "title": uploader,
                        "plot": ch_desc.replace('\n', ' <br/>'),
                        "season": "1", "episode": "-1",
                        "landscape": ch_land, "poster": ch_post, "studio": "Youtube"
                    }).make_nfo()
                    chan_nfo = True

            logger.debug("NFO", f"Creating episode NFO for: {title}")
            n.nfo("episode", folder, {
                "item_name": sanitize(title),
                "title": sanitize(title),
                "upload_date": up_date,
                "year": yr,
                "plot": desc.replace('\n', ' <br/>\n '),
                "season": "1", "episode": "",
                "preview": thumb
            }).make_nfo()

            if not os.path.isfile(path):
                with file_lock:
                    f.Folders().write_file(path, content)
                proc_count += 1
                logger.debug("STRM", f"Created STRM file: {sanitize(title)}")

        except Exception as e:
            logger.error("PROCESS", f"Failed to process video: {vid.get('id', 'unknown')}",
                         extra_data={"error": str(e)})

    logger.info("PROCESS", f"Successfully processed {proc_count} new videos for channel: {yt.channel_name}")


def to_strm(method: str):
    logger.info("STRM", f"Starting STRM generation with method: {method}")
    logger.info("STRM", f"Processing {len(channels)} channels")

    data_list = []
    for ch in channels:
        logger.info("FETCH", f"Fetching data for channel: {ch}")
        yt = Youtube(ch)
        vids = yt.get_results()

        channel_summary = {
            "name": yt.channel_name,
            "url": yt.channel_url,
            "videos": len(vids),
            "has_poster": bool(yt.channel_poster),
            "has_landscape": bool(yt.channel_landscape)
        }
        logger.info("SUMMARY", f"Channel summary: {yt.channel_name}", extra_data=channel_summary)

        if vids:
            data_list.append((yt, vids, method))
        else:
            logger.warning("FETCH", f"No videos found for channel: {ch}")

    if data_list:
        logger.info("THREADS", f"Starting parallel processing with {len(data_list)} threads")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(process_channel_videos, d): d[0].channel_name for d in data_list}

            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    fut.result()
                    logger.info("COMPLETE", f"Successfully completed processing for channel: {name}")
                except Exception as e:
                    logger.error("THREAD", f"Thread failed for channel: {name}",
                                 extra_data={"error": str(e)})

    logger.info("STRM", "STRM generation completed successfully")


def direct(youtube_id: str, remote_addr: str):
    now, key = time.time(), f"{remote_addr}_{youtube_id}"
    if key not in recent_requests:
        logger.info("REQUEST", f"New direct request from {remote_addr} for video: {youtube_id}")
        recent_requests[key] = now

    if '-audio' not in youtube_id:
        # Video handling
        cmd = cmd_builder.build(
            '-j',
            '--extractor-args', 'youtube:player-client=default,web_safari',
            f'https://www.youtube.com/watch?v={youtube_id}'
        )
        logger.debug("DIRECT", f"Fetching manifest info for video: {youtube_id}")

        try:
            info = json.loads(w.Worker(cmd).output())
            m3u8 = next((f["manifest_url"] for f in info.get("formats", []) if "manifest_url" in f), None)

            if not m3u8:
                logger.warning("DIRECT", f"No manifest found, using fallback SD for video: {youtube_id}")
                cmd = cmd_builder.build_url_extraction(
                    f'https://www.youtube.com/watch?v={youtube_id}',
                    'best'
                )
                sd_url = w.Worker(cmd).output().strip()
                logger.info("DIRECT", f"Redirecting to SD URL for video: {youtube_id}")
                return redirect(sd_url, 301)

            resp = requests.get(m3u8, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                filtered = filter_and_modify_bandwidth(resp.text)
                headers = {
                    'Content-Type': 'application/vnd.apple.mpegurl',
                    'Content-Disposition': 'inline; filename="playlist.m3u8"',
                    'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': '0'
                }
                logger.info("DIRECT", f"Serving HLS manifest for video: {youtube_id}")
                return Response(filtered, mimetype='application/vnd.apple.mpegurl', headers=headers)

        except Exception as e:
            logger.error("DIRECT", f"Video request failed for: {youtube_id}",
                         extra_data={"error": str(e)})
    else:
        # Audio handling
        s_id = youtube_id.split('-audio')[0]
        cmd = cmd_builder.build_url_extraction(
            f'https://www.youtube.com/watch?v={s_id}',
            'bestaudio'
        )
        logger.debug("DIRECT", f"Fetching audio URL for video: {s_id}")

        try:
            url = w.Worker(cmd).output().strip()
            logger.info("DIRECT", f"Redirecting to audio URL for video: {s_id}")
            return redirect(url, 301)
        except Exception as e:
            logger.error("DIRECT", f"Audio direct failed for video: {s_id}",
                         extra_data={"error": str(e)})
            abort(404)

    logger.error("DIRECT", f"All methods failed for video: {youtube_id}")
    return ("Manifest URL not found or failed to redirect.", 404)


def bridge(youtube_id: str):
    s_id = youtube_id.split('-audio')[0]
    url = f'https://www.youtube.com/watch?v={s_id}'
    logger.info("BRIDGE", f"Starting bridge stream for video: {s_id}")

    def gen():
        start = time.time()
        buf, sent = [], False

        # Build stream command
        stream_kwargs = {
            'format': 'bestaudio' if '-audio' in youtube_id else 'bestvideo+bestaudio'
        }
        if cfg.get("sponsorblock"):
            stream_kwargs.update({
                'sponsorblock': True,
                'sponsorblock_cats': cfg.get('sponsorblock_cats', '')
            })

        cmd = cmd_builder.build_stream(url, **stream_kwargs)
        logger.debug("BRIDGE", f"Bridge command: {' '.join(cmd)}")

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        time.sleep(3)
        try:
            while True:
                chunk = proc.stdout.read(1024)
                if not chunk:
                    break
                buf.append(chunk)
                if not sent and time.time() > start + 3:
                    sent = True
                    for _ in range(len(buf)):
                        yield buf.pop(0)
                elif sent:
                    yield buf.pop(0)
                proc.poll()
        finally:
            proc.kill()
            logger.info("BRIDGE", f"Bridge stream ended for video: {s_id}")

    return Response(stream_with_context(gen()), mimetype="video/mp4")


def download(youtube_id: str):
    s_id = youtube_id.split('-audio')[0]
    temp = os.path.join(os.getcwd(), 'temp')
    os.makedirs(temp, exist_ok=True)
    logger.info("DOWNLOAD", f"Starting download for video: {s_id}")

    # Build download command
    download_kwargs = {
        'format': 'bestaudio' if '-audio' in youtube_id else 'bv*+ba+ba.2',
        'output': os.path.join(temp, '%(' + 'title)s.%(ext)s')
    }
    if cfg.get("sponsorblock"):
        download_kwargs.update({
            'sponsorblock': True,
            'sponsorblock_cats': cfg.get('sponsorblock_cats', '')
        })

    cmd = cmd_builder.build_download(f'https://www.youtube.com/watch?v={s_id}', **download_kwargs)
    logger.debug("DOWNLOAD", f"Download command: {' '.join(cmd)}")

    try:
        w.Worker(cmd).call()

        # Get filename
        fn_cmd = cmd_builder.build_metadata_extraction(
            f'https://www.youtube.com/watch?v={s_id}',
            'filename'
        )
        fname = w.Worker(fn_cmd).output().strip()
        path = os.path.join(temp, fname)
        logger.info("DOWNLOAD", f"Download completed successfully: {path}")
        return send_file(path)
    except Exception as e:
        logger.error("DOWNLOAD", f"Download failed for video: {s_id}",
                     extra_data={"error": str(e)})
        abort(500, description="Download failed")


def main():
    """Main function for standalone execution"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='YouTube STRM Generator')
    parser.add_argument('--method', choices=['direct', 'bridge', 'download'],
                        default='direct', help='Streaming method to use')
    parser.add_argument('--generate-strm', action='store_true',
                        help='Generate STRM files for all configured channels')
    parser.add_argument('--channel', type=str,
                        help='Process a specific channel (overrides config)')
    parser.add_argument('--video-id', type=str,
                        help='Get direct URL for a specific video ID')
    parser.add_argument('--config', type=str,
                        help='Path to config file (default: ./plugins/youtube/config.json)')
    parser.add_argument('--channels-file', type=str,
                        help='Path to channels file')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        default='INFO', help='Set logging level')
    parser.add_argument('--test-channel', type=str,
                        help='Test a single channel and show results without creating files')

    args = parser.parse_args()

    # Update global logger level if specified
    global logger
    if args.log_level:
        new_level = LOG_LEVEL_MAP.get(args.log_level, LogLevel.INFO)
        logger.min_level = new_level
        logger.info("MAIN", f"Log level set to: {args.log_level}")

    # Override config paths if specified
    global cfg, channels
    if args.config:
        try:
            cfg = c.config(args.config).get_config()
            logger.info("MAIN", f"Loaded config from: {args.config}")
        except Exception as e:
            logger.error("MAIN", f"Failed to load config: {args.config}", extra_data={"error": str(e)})
            sys.exit(1)

    if args.channels_file:
        try:
            channels = c.config(args.channels_file).get_channels()
            logger.info("MAIN", f"Loaded channels from: {args.channels_file}")
        except Exception as e:
            logger.error("MAIN", f"Failed to load channels: {args.channels_file}", extra_data={"error": str(e)})
            sys.exit(1)

    # Handle specific channel override
    if args.channel:
        channels = [args.channel]
        logger.info("MAIN", f"Processing single channel: {args.channel}")

    try:
        # Test a single channel without creating files
        if args.test_channel:
            logger.info("MAIN", f"Testing channel: {args.test_channel}")
            yt = Youtube(args.test_channel)
            videos = yt.get_results()

            print(f"\n=== Channel Test Results ===")
            print(f"Channel: {yt.channel_name}")
            print(f"URL: {yt.channel_url}")
            print(f"Description: {yt.channel_description[:100]}..." if yt.channel_description else "No description")
            print(f"Poster: {yt.channel_poster}")
            print(f"Landscape: {yt.channel_landscape}")
            print(f"Videos found: {len(videos)}")

            if videos:
                print(f"\nFirst 5 videos:")
                for i, video in enumerate(videos[:5]):
                    print(f"{i + 1}. {video['title']} ({video['id']})")
                    print(f"   Upload date: {video['upload_date']}")
                    print(f"   Thumbnail: {video['thumbnail']}")
                    print()

            logger.info("MAIN", "Channel test completed")
            return

        # Get direct URL for a specific video
        if args.video_id:
            logger.info("MAIN", f"Getting direct URL for video: {args.video_id}")

            if '-audio' in args.video_id:
                s_id = args.video_id.split('-audio')[0]
                cmd = cmd_builder.build_url_extraction(
                    f'https://www.youtube.com/watch?v={s_id}',
                    'bestaudio'
                )
            else:
                cmd = cmd_builder.build_url_extraction(
                    f'https://www.youtube.com/watch?v={args.video_id}',
                    'best'
                )

            try:
                url = w.Worker(cmd).output().strip()
                print(f"\nDirect URL for {args.video_id}:")
                print(url)
                logger.info("MAIN", f"Direct URL retrieved successfully for: {args.video_id}")
            except Exception as e:
                logger.error("MAIN", f"Failed to get direct URL for: {args.video_id}",
                             extra_data={"error": str(e)})
                sys.exit(1)
            return

        # Generate STRM files
        if args.generate_strm:
            if not channels:
                logger.error("MAIN", "No channels configured. Please check your channels file.")
                sys.exit(1)

            logger.info("MAIN", f"Starting STRM generation for {len(channels)} channels")
            to_strm(args.method)
            logger.info("MAIN", "STRM generation completed successfully")
            return

        # If no specific action, show help
        parser.print_help()

    except KeyboardInterrupt:
        logger.info("MAIN", "Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error("MAIN", "Unexpected error occurred", extra_data={"error": str(e)})
        sys.exit(1)


def check_dependencies():
    """Check if all required dependencies are available"""
    missing_deps = []

    try:
        import yt_dlp
    except ImportError:
        missing_deps.append("yt-dlp")

    try:
        from clases.config import config
        from clases.worker import worker
        from clases.folders import folders
        from clases.nfo import nfo
    except ImportError as e:
        missing_deps.append(f"clases module: {str(e)}")

    try:
        from sanitize_filename import sanitize
    except ImportError:
        missing_deps.append("sanitize-filename")

    if missing_deps:
        print("Missing dependencies:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print("\nPlease install missing dependencies before running.")
        return False

    return True


def create_sample_config():
    """Create a sample configuration file"""
    sample_config = {
        "strm_output_folder": "./strm_files",
        "days_dateafter": "30",
        "videos_limit": 50,
        "cookies": "cookies-from-browser",
        "cookie_value": "chromium",
        "proxy": False,
        "proxy_url": "",
        "max_workers": 4,
        "request_timeout": 30,
        "log_level": "INFO",
        "sponsorblock": False,
        "sponsorblock_cats": "sponsor,intro,outro",
        "channels_list_file": "./channels.txt"
    }

    sample_channels = [
        "# Add YouTube channels here, one per line",
        "# Examples:",
        "# @channelname",
        "# https://www.youtube.com/@channelname",
        "# https://www.youtube.com/c/channelname",
        "# UCxxxxxxxxxxxxxxxxxxxxx (channel ID)",
        "# keyword-searchterm (search for videos)",
        "# list-PLxxxxxxxxxxxxxxxxxxxxx (playlist ID)",
        "# extractaudio-@channelname (audio only)",
        ""
    ]

    config_path = "./youtube_config.json"
    channels_path = "./youtube_channels.txt"

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(sample_config, f, indent=2)

        with open(channels_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sample_channels))

        print(f"Created sample configuration files:")
        print(f"  Config: {config_path}")
        print(f"  Channels: {channels_path}")
        print("\nEdit these files with your settings and channels, then run:")
        print(f"python youtube.py --config {config_path} --channels-file {channels_path} --generate-strm")

    except Exception as e:
        print(f"Failed to create sample config: {e}")


if __name__ == "__main__":
    print("YouTube STRM Generator - Standalone Mode")
    print("=" * 40)

    # Check if running in standalone mode and dependencies are missing
    if not check_dependencies():
        print("\nTo create sample configuration files, run with --create-config")
        response = input("Create sample config files? (y/n): ")
        if response.lower().startswith('y'):
            create_sample_config()
        sys.exit(1)

    # Check if config files exist when no arguments provided
    if len(sys.argv) == 1:
        if not os.path.exists('./plugins/youtube/config.json'):
            print("No configuration found. Creating sample configuration files...")
            create_sample_config()
            sys.exit(0)

    main()