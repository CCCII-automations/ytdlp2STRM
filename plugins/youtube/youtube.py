#!/usr/bin/env python3
"""
YouTube to STRM Downloader - Refactored Version
This script downloads YouTube videos/playlists and creates STRM files for media servers.

Usage Examples:
    # Process all channels in config
    python youtube_downloader.py

    # Process single channel
    python youtube_downloader.py --channel "@channelname"

    # Process playlist
    python youtube_downloader.py --playlist "PLxxxxxxxxxxxxx"

    # Extract audio only
    python youtube_downloader.py --channel "extractaudio-@channelname"

    # Search by keyword
    python youtube_downloader.py --keyword "python tutorial"
"""

import os
import json
import time
import platform
import subprocess
import requests
import html
import re
import unicodedata
import shutil
from datetime import datetime
from cachetools import TTLCache
from pathlib import Path
import argparse
import sys

root_dir = Path(__file__).resolve().parents[2]
sys.path.append(str(root_dir))

from clases.config import config as c
from clases.worker import worker as w
from clases.folders import folders as f
from clases.nfo import nfo as n
from clases.log import log as l

from sanitize_filename import sanitize
from flask import stream_with_context, Response, send_file, redirect, abort, request

# Initialize cache for recent requests
recent_requests = TTLCache(maxsize=200, ttl=30)

# Load configurations
ytdlp2strm_config = c.config('./config/config.json').get_config()
config = c.config('./plugins/youtube/config.json').get_config()
channels = c.config(config["channels_list_file"]).get_channels()

# Configuration variables
media_folder = config["strm_output_folder"]
days_dateafter = config["days_dateafter"]
videos_limit = config["videos_limit"]

# Cookie configuration
try:
    cookies = config["cookies"]
    cookie_value = config["cookie_value"]
except:
    cookies = 'cookies-from-browser'
    cookie_value = 'chromium'  # Changed to Chromium as requested

source_platform = "youtube"
host = ytdlp2strm_config['ytdlp2strm_host']
port = ytdlp2strm_config['ytdlp2strm_port']

# Docker environment check
SECRET_KEY = os.environ.get('AM_I_IN_A_DOCKER_CONTAINER', False)
DOCKER_PORT = os.environ.get('DOCKER_PORT', False)
if SECRET_KEY:
    port = DOCKER_PORT

# Proxy configuration
if 'proxy' in config:
    proxy = config['proxy']
    proxy_url = config['proxy_url']
else:
    proxy = False
    proxy_url = ""


class Youtube:
    """Main YouTube processing class"""

    def __init__(self, channel=None):
        self.channel = channel
        self.channel_url = None
        self.channel_name = None
        self.channel_description = None
        self.channel_poster = None
        self.channel_landscape = None
        self.sleep_interval = config.get('sleep_interval', 1)  # Add sleep interval

    def clean_channel_name(self, name):
        """Clean channel name to UTF-8 without special characters"""
        if not name:
            return "Unknown_Channel"

        # Normalize to NFD (decomposed) and encode/decode to remove accents
        name = unicodedata.normalize('NFD', name)
        name = name.encode('ascii', 'ignore').decode('utf-8')

        # Remove special characters, keep only alphanumeric, spaces, and basic punctuation
        name = re.sub(r'[^\w\s\-_]', '', name)
        name = name.strip()

        # Replace spaces with underscores
        name = name.replace(' ', '_')

        l.log("youtube", f"Cleaned channel name: {name}")
        return name

    def create_channel_directory(self, channel_id):
        """Create channel directory if it doesn't exist"""
        clean_name = self.clean_channel_name(self.channel_name)
        folder_name = f"{clean_name}_{channel_id}"
        folder_path = os.path.join(media_folder, folder_name)

        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            l.log("youtube", f"Created directory: {folder_path}")
        else:
            l.log("youtube", f"Directory already exists: {folder_path}")

        return folder_path, folder_name

    def download_channel_poster(self, folder_path):
        """Download and save channel poster"""
        if self.channel_poster:
            poster_path = os.path.join(folder_path, 'poster.jpg')
            if not os.path.exists(poster_path):
                try:
                    response = requests.get(self.channel_poster, timeout=10)
                    if response.status_code == 200:
                        with open(poster_path, 'wb') as f:
                            f.write(response.content)
                        l.log("youtube", f"Downloaded channel poster: {poster_path}")
                except Exception as e:
                    l.log("youtube", f"Failed to download poster: {str(e)}")

    def download_thumbnail(self, video_id, thumbnail_url, folder_path, video_name):
        """Download and save video thumbnail at 10+ seconds"""
        thumbnail_path = os.path.join(folder_path, f"{sanitize(video_name)}.jpg")

        # Try to get thumbnail from 10+ seconds into the video
        command = [
            'yt-dlp',
            '--write-thumbnail',
            '--convert-thumbnails', 'jpg',
            '--skip-download',
            '--output', thumbnail_path.replace('.jpg', ''),
            f'https://www.youtube.com/watch?v={video_id}'
        ]

        self.set_proxy(command)
        self.set_cookies(command)

        try:
            # First try to download the thumbnail
            result = w.Worker(command).call()

            # If standard thumbnail doesn't work, try to extract frame at 10 seconds
            if not os.path.exists(thumbnail_path):
                l.log("youtube", f"Standard thumbnail failed, extracting frame at 10 seconds")

                # Get video URL first
                url_command = [
                    'yt-dlp',
                    '-f', 'best',
                    '--get-url',
                    f'https://www.youtube.com/watch?v={video_id}'
                ]
                self.set_proxy(url_command)
                self.set_cookies(url_command)

                video_url = w.Worker(url_command).output().strip()

                # Extract frame using ffmpeg
                ffmpeg_command = [
                    'ffmpeg',
                    '-ss', '10',  # Start at 10 seconds
                    '-i', video_url,
                    '-vframes', '1',
                    '-q:v', '2',
                    thumbnail_path
                ]

                subprocess.run(ffmpeg_command, capture_output=True)

            if os.path.exists(thumbnail_path):
                l.log("youtube", f"Thumbnail saved: {thumbnail_path}")
            else:
                # Fallback to URL download
                if thumbnail_url:
                    response = requests.get(thumbnail_url, timeout=10)
                    if response.status_code == 200:
                        with open(thumbnail_path, 'wb') as f:
                            f.write(response.content)
                        l.log("youtube", f"Downloaded thumbnail from URL: {thumbnail_path}")

        except Exception as e:
            l.log("youtube", f"Error downloading thumbnail: {str(e)}")

    def check_and_update_existing_files(self, folder_path, video_id, video_info):
        """Check if files exist and update if needed"""
        video_name = sanitize(video_info['title'])

        # Check STRM file
        strm_path = os.path.join(folder_path, f"{video_name}.strm")

        # Check NFO file
        nfo_path = os.path.join(folder_path, f"{video_name}.nfo")

        # Check thumbnail
        thumbnail_path = os.path.join(folder_path, f"{video_name}.jpg")

        needs_update = False

        if not os.path.exists(strm_path):
            l.log("youtube", f"STRM file missing for {video_name}")
            needs_update = True

        if not os.path.exists(nfo_path):
            l.log("youtube", f"NFO file missing for {video_name}")
            needs_update = True

        if not os.path.exists(thumbnail_path):
            l.log("youtube", f"Thumbnail missing for {video_name}")
            self.download_thumbnail(video_id, video_info['thumbnail'], folder_path, video_name)

        return needs_update

    def get_results(self):
        """Main method to get channel/playlist results"""
        l.log("youtube", f"Processing: {self.channel}")

        if 'extractaudio-' in self.channel:
            islist = False
            self.channel_url = self.channel.replace('extractaudio-', '')

            if 'list-' in self.channel:
                islist = True
                self.channel_url = self.channel.replace('list-', '')
                if not 'www.youtube' in self.channel_url:
                    self.channel_url = f'https://www.youtube.com/playlist?list={self.channel_url}'
            else:
                if not 'www.youtube' in self.channel_url:
                    self.channel_url = f'https://www.youtube.com/{self.channel_url}'

            self.channel_name = self.get_channel_name()
            self.channel_description = self.get_channel_description() if not islist else f'Playlist {self.channel_name}'
            thumbs = self.get_channel_images()
            self.channel_poster = thumbs['poster']
            self.channel_landscape = thumbs['landscape']

            return self.get_channel_audios() if not islist else self.get_list_audios()

        elif 'keyword' in self.channel:
            return self.get_keyword_videos()

        elif 'list' in self.channel:
            self.channel_url = self.channel.replace('list-', '')
            if not 'www.youtube' in self.channel_url:
                self.channel_url = f'https://www.youtube.com/playlist?list={self.channel_url}'

            self.channel_name = self.get_channel_name()
            self.channel_description = f'Playlist {self.channel_name}'
            thumbs = self.get_channel_images()
            self.channel_poster = thumbs['poster']
            self.channel_landscape = thumbs['landscape']
            return self.get_list_videos()

        else:
            self.channel_url = self.channel
            if not 'www.youtube' in self.channel:
                self.channel_url = f'https://www.youtube.com/{self.channel}'

            self.channel_name = self.get_channel_name()
            self.channel_description = self.get_channel_description()
            thumbs = self.get_channel_images()
            self.channel_poster = thumbs['poster']
            self.channel_landscape = thumbs['landscape']
            return self.get_channel_videos()

    def get_list_videos(self):
        """Get videos from playlist"""
        command = [
            'yt-dlp',
            '--compat-options', 'no-youtube-channel-redirect',
            '--compat-options', 'no-youtube-unavailable-videos',
            '--playlist-start', '1',
            '--playlist-end', str(videos_limit),
            '--sleep-interval', str(self.sleep_interval),  # Add sleep
            '--no-warning',
            '--dump-json',
            self.channel_url
        ]

        self.set_proxy(command)
        self.set_cookies(command)

        result = w.Worker(command).output()
        videos = []

        for line in result.split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    video = {
                        'id': data.get('id'),
                        'title': data.get('title'),
                        'upload_date': data.get('upload_date'),
                        'thumbnail': data.get('thumbnail'),
                        'description': data.get('description'),
                        'channel_id': self.channel_url.split('list=')[1],
                        'uploader_id': sanitize(self.channel_name)
                    }
                    videos.append(video)
                    l.log("youtube", f"Found video: {video['title']}")
                except json.JSONDecodeError:
                    l.log("youtube", f"Error parsing JSON: {line}")

        return videos

    def get_keyword_videos(self):
        """Search videos by keyword"""
        keyword = self.channel.split('-')[1]
        command = [
            'yt-dlp',
            '-f', 'best',
            f'ytsearch{videos_limit}:["{keyword}"]',
            '--compat-options', 'no-youtube-channel-redirect',
            '--compat-options', 'no-youtube-unavailable-videos',
            '--sleep-interval', str(self.sleep_interval),
            '--no-warning',
            '--dump-json'
        ]

        self.set_proxy(command)
        self.set_cookies(command)

        result = w.Worker(command).output()
        videos = []

        for line in result.split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    video = {
                        'id': data.get('id'),
                        'title': data.get('title'),
                        'upload_date': data.get('upload_date'),
                        'thumbnail': data.get('thumbnail'),
                        'description': data.get('description'),
                        'channel_id': data.get('channel_id'),
                        'uploader_id': data.get('uploader_id')
                    }
                    videos.append(video)
                except json.JSONDecodeError:
                    pass

        return videos

    def get_channel_audios(self):
        """Get audio from channel"""
        cu = self.channel_url
        if not '/streams' in self.channel_url:
            cu = f'{self.channel_url}/videos'

        command = [
            'yt-dlp',
            '--compat-options', 'no-youtube-channel-redirect',
            '--compat-options', 'no-youtube-unavailable-videos',
            '--dateafter', f"today-{days_dateafter}days",
            '--playlist-start', '1',
            '--playlist-end', str(videos_limit),
            '--sleep-interval', str(self.sleep_interval),
            '--no-warning',
            '--dump-json',
            cu
        ]

        self.set_proxy(command)
        self.set_cookies(command)

        result = w.Worker(command).output()
        videos = []

        for line in result.split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    video = {
                        'id': f"{data.get('id')}-audio",
                        'title': data.get('title'),
                        'upload_date': data.get('upload_date'),
                        'thumbnail': data.get('thumbnail'),
                        'description': data.get('description'),
                        'channel_id': data.get('channel_id'),
                        'uploader_id': data.get('uploader_id')
                    }
                    videos.append(video)
                except json.JSONDecodeError:
                    pass

        return videos

    def get_list_audios(self):
        """Get audio from playlist"""
        command = [
            'yt-dlp',
            '--compat-options', 'no-youtube-channel-redirect',
            '--compat-options', 'no-youtube-unavailable-videos',
            '--playlist-start', '1',
            '--playlist-end', str(videos_limit),
            '--sleep-interval', str(self.sleep_interval),
            '--no-warning',
            '--dump-json',
            self.channel_url
        ]

        self.set_proxy(command)
        self.set_cookies(command)

        result = w.Worker(command).output()
        videos = []

        for line in result.split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    video = {
                        'id': f"{data.get('id')}-audio",
                        'title': data.get('title'),
                        'upload_date': data.get('upload_date'),
                        'thumbnail': data.get('thumbnail'),
                        'description': data.get('description'),
                        'channel_id': self.channel_url.split('list=')[1],
                        'uploader_id': sanitize(self.channel_name)
                    }
                    videos.append(video)
                except json.JSONDecodeError:
                    pass

        return videos

    def get_channel_videos(self):
        """Get videos from channel"""
        cu = self.channel_url if '/streams' in self.channel_url else f'{self.channel_url}/videos'

        command = [
            'yt-dlp',
            '--compat-options', 'no-youtube-channel-redirect',
            '--compat-options', 'no-youtube-unavailable-videos',
            '--dateafter', f"today-{days_dateafter}days",
            '--playlist-start', '1',
            '--playlist-end', str(videos_limit),
            '--sleep-interval', str(self.sleep_interval),
            '--no-warning',
            '--dump-json',
            cu
        ]

        self.set_proxy(command)
        self.set_cookies(command)

        result = w.Worker(command).output()
        videos = []

        for line in result.split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    video = {
                        'id': data.get('id'),
                        'title': data.get('title'),
                        'upload_date': data.get('upload_date'),
                        'thumbnail': data.get('thumbnail'),
                        'description': data.get('description'),
                        'channel_id': data.get('channel_id'),
                        'uploader_id': data.get('uploader_id')
                    }
                    videos.append(video)
                    l.log("youtube", f"Found video: {video['title']}")
                except json.JSONDecodeError:
                    l.log("youtube", f"Error parsing video JSON")

        return videos

    def get_channel_name(self):
        """Get channel or playlist name"""
        if 'playlist' in self.channel_url:
            command = [
                'yt-dlp',
                '--compat-options', 'no-youtube-unavailable-videos',
                '--print', '%(playlist_title)s',
                '--playlist-items', '1',
                '--restrict-filenames',
                '--ignore-errors',
                '--no-warnings',
                '--compat-options', 'no-youtube-channel-redirect',
                self.channel_url
            ]
        else:
            command = [
                'yt-dlp',
                '--compat-options', 'no-youtube-unavailable-videos',
                '--print', '%(channel)s',
                '--restrict-filenames',
                '--ignore-errors',
                '--no-warnings',
                '--playlist-items', '1',
                '--compat-options', 'no-youtube-channel-redirect',
                self.channel_url
            ]

        self.set_proxy(command)
        self.set_cookies(command)

        self.channel_name = w.Worker(command).output().strip()
        return self.channel_name

    def get_channel_description(self):
        """Get channel description and save to file"""
        desc_filename = f"{self.clean_channel_name(self.channel_name)}_description.txt"
        desc_path = os.path.join(media_folder, desc_filename)

        command = [
            'yt-dlp',
            self.channel_url,
            '--write-description',
            '--playlist-items', '0',
            '--output', desc_path.replace('.txt', '')
        ]

        self.set_proxy(command)
        self.set_cookies(command)

        try:
            # Execute command
            w.Worker(command).call()

            # Read the description file
            actual_desc_path = desc_path.replace('.txt', '.description')
            if os.path.exists(actual_desc_path):
                with open(actual_desc_path, 'r', encoding='utf-8') as f:
                    self.channel_description = f.read()

                # Save to permanent location
                permanent_desc_path = desc_path
                shutil.move(actual_desc_path, permanent_desc_path)
                l.log("youtube", f"Saved channel description to: {permanent_desc_path}")
            else:
                self.channel_description = "No description available"

        except Exception as e:
            l.log("youtube", f"Error getting channel description: {str(e)}")
            self.channel_description = "Error retrieving description"

        return self.channel_description

    def get_channel_images(self):
        """Get channel poster and landscape images"""
        command = [
            'yt-dlp',
            '--list-thumbnails',
            '--restrict-filenames',
            '--ignore-errors',
            '--no-warnings',
            '--playlist-items', '0',
            self.channel_url
        ]

        self.set_proxy(command)
        self.set_cookies(command)

        landscape = None
        poster = None

        try:
            output = w.Worker(command).output()
            lines = output.split('\n')

            thumbnails = []
            headers = []

            for i, line in enumerate(lines):
                line = ' '.join(line.split())
                if not '[' in line and line.strip():
                    data = line.split()
                    if i == 0 or 'ID' in data[0]:
                        headers = data
                    else:
                        if len(data) >= len(headers):
                            row = {}
                            for j, d in enumerate(data[:len(headers)]):
                                row[headers[j]] = d
                            thumbnails.append(row)

            # Find poster (avatar)
            for thumb in thumbnails:
                if thumb.get('ID') == 'avatar_uncropped':
                    poster = thumb.get('URL')
                    break

            # Find landscape (banner)
            for thumb in thumbnails:
                if thumb.get('ID') == 'banner_uncropped':
                    landscape = thumb.get('URL')
                    break

        except Exception as e:
            l.log("youtube", f"Error getting channel images: {str(e)}")

        return {
            "landscape": landscape,
            "poster": poster
        }

    def set_proxy(self, command):
        """Add proxy to command if configured"""
        if proxy and proxy_url:
            command.extend(['--proxy', proxy_url])

    def set_cookies(self, command):
        """Add cookies to command"""
        command.extend([f'--{cookies}', cookie_value])

    def write_video_files(self, video_info, folder_path, folder_name, channel_id):
        """Write individual video files (STRM, NFO, thumbnail)"""
        video_id = video_info['id']
        video_name = sanitize(video_info['title'])

        # Write STRM file
        strm_path = os.path.join(folder_path, f"{video_name}.strm")
        strm_content = f'http://{host}:{port}/{source_platform}/direct/{video_id}'

        with open(strm_path, 'w', encoding='utf-8') as f:
            f.write(strm_content)
        l.log("youtube", f"Created STRM file: {strm_path}")

        # Write NFO file
        try:
            date = datetime.strptime(video_info['upload_date'], '%Y%m%d')
            upload_date = date.strftime('%Y-%m-%d')
            year = date.year
        except:
            upload_date = datetime.now().strftime('%Y-%m-%d')
            year = datetime.now().year

        nfo_data = {
            "item_name": video_name,
            "title": video_name,
            "upload_date": upload_date,
            "year": year,
            "plot": video_info.get('description', '').replace('\n', ' <br/>\n '),
            "season": "1",
            "episode": "",
            "preview": video_info.get('thumbnail', '')
        }

        # Create NFO
        n.nfo("episode", folder_path, nfo_data).make_nfo()
        l.log("youtube", f"Created NFO file for: {video_name}")

        # Download thumbnail
        self.download_thumbnail(
            video_id.replace('-audio', ''),
            video_info.get('thumbnail'),
            folder_path,
            video_name
        )

        # Add sleep to prevent rate limiting
        time.sleep(self.sleep_interval)


def filter_and_modify_bandwidth(m3u8_content):
    """Filter M3U8 content for optimal bandwidth"""
    lines = m3u8_content.splitlines()

    highest_bandwidth = 0
    best_video_info = None
    best_video_url = None

    media_lines = []

    high_audio = False
    sd_audio = ""

    for i in range(len(lines)):
        line = lines[i]

        if line.startswith("#EXT-X-STREAM-INF:"):
            info = line
            url = lines[i + 1]
            bandwidth = int(info.split("BANDWIDTH=")[1].split(",")[0])

            if bandwidth > highest_bandwidth:
                highest_bandwidth = bandwidth
                best_video_info = info.replace(f"BANDWIDTH={bandwidth}", "BANDWIDTH=279001")
                best_video_url = url

        if line.startswith("#EXT-X-MEDIA:URI"):
            if '234' in line:
                high_audio = True
                media_lines.append(line)
            else:
                sd_audio = line

    if not high_audio and sd_audio:
        media_lines.append(sd_audio)

    # Create the final M3U8 content
    final_m3u8 = "#EXTM3U\n#EXT-X-INDEPENDENT-SEGMENTS\n"

    # Add all EXT-X-MEDIA lines
    for media_line in media_lines:
        final_m3u8 += f"{media_line}\n"

    if best_video_info and best_video_url:
        final_m3u8 += f"{best_video_info}\n{best_video_url}\n"

    return final_m3u8


def clean_text(text):
    """Clean text from special characters"""
    text = html.escape(text)
    text = re.sub(r'[^\w\s\[\]\(\)\-\_\'\"\/\.\:\;\,]', '', text)
    return text


def video_id_exists_in_content(media_folder, video_id):
    """Check if video ID exists in any STRM file"""
    for root, dirs, files in os.walk(media_folder):
        for file in files:
            if file.endswith(".strm"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        if video_id in f.read():
                            return True
                except:
                    pass
    return False


def to_strm(method):
    """Main function to process channels and create STRM files"""
    for youtube_channel in channels:
        yt = Youtube(youtube_channel)

        l.log("youtube", " --------------- ")
        l.log("youtube", f'Working on {youtube_channel}...')

        videos = yt.get_results()
        channel_name = yt.channel_name
        channel_url = yt.channel_url
        channel_description = yt.channel_description

        l.log("youtube", f'Channel URL: {channel_url}')
        l.log("youtube", f'Channel Name: {channel_name}')
        l.log("youtube", f'Channel Poster: {yt.channel_poster}')
        l.log("youtube", f'Channel Landscape: {yt.channel_landscape}')
        l.log("youtube", 'Channel Description:')
        l.log("youtube", channel_description)

        if videos:
            l.log("youtube", f'Videos detected: {len(videos)}')

            # Process first video to get channel info if needed
            first_video = videos[0]
            channel_id = first_video['channel_id']

            # Step 1: Create channel directory
            folder_path, folder_name = yt.create_channel_directory(channel_id)

            # Step 2: Download channel poster
            yt.download_channel_poster(folder_path)

            # Step 3: Create channel NFO
            channel_nfo_data = {
                "title": channel_name,
                "plot": channel_description.replace('\n', ' <br/>'),
                "season": "1",
                "episode": "-1",
                "landscape": yt.channel_landscape,
                "poster": yt.channel_poster,
                "studio": "Youtube"
            }

            n.nfo("tvshow", folder_path, channel_nfo_data).make_nfo()
            l.log("youtube", "Created channel NFO file")

            # Step 4 & 5: Process videos one by one
            for video in videos:
                video_id = video['id']

                # Check if video already exists
                if video_id_exists_in_content(folder_path, video_id):
                    l.log("youtube", f'Video {video_id} already exists, checking for updates...')

                    # Step 8: Check and update existing files
                    needs_update = yt.check_and_update_existing_files(folder_path, video_id, video)

                    if not needs_update:
                        continue

                # Step 6: Write files individually
                yt.write_video_files(video, folder_path, folder_name, channel_id)

        else:
            l.log("youtube", "No videos detected...")


def direct(youtube_id, remote_addr):
    """Direct streaming handler for YouTube videos"""
    current_time = time.time()
    cache_key = f"{remote_addr}_{youtube_id}"

    # Check if the request is already cached
    if cache_key not in recent_requests:
        log_text = f'[{remote_addr}] Playing {youtube_id}'
        l.log("youtube", log_text)
        recent_requests[cache_key] = current_time

    if '-audio' not in youtube_id:
        command = [
            'yt-dlp',
            '-j',
            '--no-warnings',
            '--extractor-args', 'youtube:player-client=default,web_safari',
            f'https://www.youtube.com/watch?v={youtube_id}'
        ]
        Youtube().set_cookies(command)
        Youtube().set_proxy(command)

        full_info_json_str = w.Worker(command).output()
        m3u8_url = None

        try:
            full_info_json = json.loads(full_info_json_str)
            for fmt in full_info_json["formats"]:
                if "manifest_url" in fmt.keys():
                    m3u8_url = fmt["manifest_url"]
                    break
        except:
            pass

        if not m3u8_url:
            log_text = ('No manifest detected. Check your cookies config.')
            l.log("youtube", log_text)

            command = [
                'yt-dlp',
                '-f', 'best',
                '--get-url',
                '--no-warnings',
                f'https://www.youtube.com/watch?v={youtube_id}'
            ]
            Youtube().set_proxy(command)
            Youtube().set_cookies(command)

            sd_url = w.Worker(command).output()
            return redirect(sd_url.strip(), 301)
        else:
            response = requests.get(m3u8_url)
            if response.status_code == 200:
                m3u8_content = response.text
                filtered_content = filter_and_modify_bandwidth(m3u8_content)
                headers = {
                    'Content-Type': 'application/vnd.apple.mpegurl',
                    'Content-Disposition': 'inline; filename="playlist.m3u8"',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }

                return Response(filtered_content, mimetype='application/vnd.apple.mpegurl', headers=headers)
    else:
        # Audio handling
        s_youtube_id = youtube_id.split('-audio')[0]
        command = [
            'yt-dlp',
            '-f', 'bestaudio',
            '--get-url',
            '--no-warnings',
            f'https://www.youtube.com/watch?v={s_youtube_id}'
        ]
        Youtube().set_cookies(command)
        Youtube().set_proxy(command)

        audio_url = w.Worker(command).output()
        return redirect(audio_url, 301)

    return "Manifest URL not found or failed to redirect.", 404


def bridge(youtube_id):
    """Bridge streaming handler for YouTube videos"""
    s_youtube_id = youtube_id.split('-audio')[0]
    s_youtube_id = f'https://www.youtube.com/watch?v={s_youtube_id}'

    def generate():
        startTime = time.time()
        buffer = []
        sentBurst = False

        if config.get("sponsorblock", False):
            command = [
                'yt-dlp', '--no-warnings', '-o', '-',
                '-f', 'bestvideo+bestaudio',
                '--sponsorblock-remove', config.get('sponsorblock_cats', 'all'),
                '--restrict-filenames',
                s_youtube_id
            ]
        else:
            command = [
                'yt-dlp', '--no-warnings', '-o', '-',
                '-f', 'best',
                '--restrict-filenames',
                s_youtube_id
            ]

        Youtube().set_proxy(command)
        Youtube().set_cookies(command)

        if '-audio' in youtube_id:
            command[5] = 'bestaudio'

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        time.sleep(3)

        try:
            while True:
                line = process.stdout.read(1024)

                if not line:
                    break

                buffer.append(line)

                # Minimum buffer time, 3 seconds
                if sentBurst is False and time.time() > startTime + 3 and len(buffer) > 0:
                    sentBurst = True
                    for i in range(0, len(buffer) - 2):
                        yield buffer.pop(0)

                elif time.time() > startTime + 3 and len(buffer) > 0:
                    yield buffer.pop(0)

                process.poll()
        finally:
            process.kill()

    return Response(
        stream_with_context(generate()),
        mimetype="video/mp4"
    )


def download(youtube_id):
    """Download handler for YouTube videos"""
    s_youtube_id = youtube_id.split('-audio')[0]
    current_dir = os.getcwd()
    temp_dir = os.path.join(current_dir, 'temp')

    # Create temp directory if it doesn't exist
    os.makedirs(temp_dir, exist_ok=True)

    if config.get("sponsorblock", False):
        command = [
            'yt-dlp',
            '-f', 'bv*+ba+ba.2',
            '-o', os.path.join(temp_dir, '%(title)s.%(ext)s'),
            '--sponsorblock-remove', config.get('sponsorblock_cats', 'all'),
            '--restrict-filenames',
            s_youtube_id
        ]
    else:
        command = [
            'yt-dlp',
            '-f', 'bv*+ba+ba.2',
            '-o', os.path.join(temp_dir, '%(title)s.%(ext)s'),
            '--restrict-filenames',
            s_youtube_id
        ]

    Youtube().set_proxy(command)
    Youtube().set_cookies(command)

    if '-audio' in youtube_id:
        command[2] = 'bestaudio'

    w.Worker(command).call()

    # Get the filename
    filename_command = [
        'yt-dlp',
        '--print', 'filename',
        '--restrict-filenames',
        f'https://www.youtube.com/watch?v={s_youtube_id}'
    ]

    filename = w.Worker(filename_command).output().strip()

    return send_file(os.path.join(temp_dir, filename))


def process_single_channel(channel_identifier):
    """Process a single channel/playlist"""
    yt = Youtube(channel_identifier)

    l.log("youtube", " --------------- ")
    l.log("youtube", f'Processing single channel: {channel_identifier}')

    videos = yt.get_results()

    if not videos:
        l.log("youtube", "No videos found")
        return

    channel_name = yt.channel_name
    channel_id = videos[0]['channel_id']

    # Create directory
    folder_path, folder_name = yt.create_channel_directory(channel_id)

    # Download poster
    yt.download_channel_poster(folder_path)

    # Create channel NFO
    channel_nfo_data = {
        "title": channel_name,
        "plot": yt.channel_description.replace('\n', ' <br/>'),
        "season": "1",
        "episode": "-1",
        "landscape": yt.channel_landscape,
        "poster": yt.channel_poster,
        "studio": "Youtube"
    }

    n.nfo("tvshow", folder_path, channel_nfo_data).make_nfo()

    # Process videos
    for video in videos:
        video_id = video['id']

        if not video_id_exists_in_content(folder_path, video_id):
            yt.write_video_files(video, folder_path, folder_name, channel_id)
        else:
            l.log("youtube", f"Video {video_id} already exists")


def main():
    """Main entry point for command line execution"""
    parser = argparse.ArgumentParser(description='YouTube to STRM Downloader')
    parser.add_argument('--channel', help='Process a single channel')
    parser.add_argument('--playlist', help='Process a playlist')
    parser.add_argument('--keyword', help='Search by keyword')
    parser.add_argument('--audio', action='store_true', help='Extract audio only')

    args = parser.parse_args()

    if args.channel:
        channel_id = args.channel
        if args.audio:
            channel_id = f"extractaudio-{channel_id}"
        process_single_channel(channel_id)
    elif args.playlist:
        playlist_id = f"list-{args.playlist}"
        if args.audio:
            playlist_id = f"extractaudio-{playlist_id}"
        process_single_channel(playlist_id)
    elif args.keyword:
        keyword_search = f"keyword-{args.keyword}"
        process_single_channel(keyword_search)
    else:
        # Process all channels from config
        to_strm('direct')


if __name__ == "__main__":
    main()