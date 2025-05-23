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

from clases.config import config as c
from clases.worker import worker as w
from clases.folders import folders as f
from clases.nfo import nfo as n
from clases.log import log as l

from sanitize_filename import sanitize
from flask import stream_with_context, Response, send_file, redirect, abort, request
from pathlib import Path
import pwd
import grp

# Caches
recent_requests = TTLCache(maxsize=500, ttl=60)
channel_cache = TTLCache(maxsize=100, ttl=3600)

# Thread lock
file_lock = threading.Lock()

# Load configs
ytdlp2strm_cfg = c.config('./config/config.json').get_config()
cfg           = c.config('./plugins/youtube/config.json').get_config()
channels      = c.config(cfg["channels_list_file"]).get_channels()

media_folder     = cfg["strm_output_folder"]
days_dateafter   = cfg["days_dateafter"]
videos_limit     = cfg["videos_limit"]
cookies          = cfg.get("cookies", "cookies-from-browser")
cookie_value     = cfg.get("cookie_value", "chromium")
proxy            = cfg.get("proxy", False)
proxy_url        = cfg.get("proxy_url", "")
MAX_WORKERS      = cfg.get("max_workers", 4)
REQUEST_TIMEOUT  = cfg.get("request_timeout", 30)
LOG_LEVEL_MAP    = {'DEBUG':0,'INFO':1,'WARNING':2,'ERROR':3}
LOG_LEVEL        = LOG_LEVEL_MAP.get(cfg.get("log_level","INFO"),1)

source_platform  = "youtube"
host             = ytdlp2strm_cfg['ytdlp2strm_host']
port             = ytdlp2strm_cfg['ytdlp2strm_port']
if os.environ.get('AM_I_IN_A_DOCKER_CONTAINER'):
    port = os.environ.get('DOCKER_PORT', port)

Path(media_folder).mkdir(parents=True, exist_ok=True)
# Get UID and GID of the current user
uid = os.getuid()
gid = os.getgid()
os.chown(media_folder, uid, gid)
os.chmod(media_folder, 0o2775)

def enhanced_log(level: str, message: str, details: Optional[Dict]=None):
    """Structured logging with levels"""
    if LOG_LEVEL_MAP[level] >= LOG_LEVEL:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = f"[{ts}] [{level}] {message}"
        if details:
            entry += f" | {json.dumps(details, indent=2)}"
        l.log("youtube", entry)
        print(entry)

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
    def __init__(self, channel: str=None):
        self.channel = channel
        self.channel_url = None
        self.channel_name = None
        self.channel_description = None
        self.channel_poster = None
        self.channel_landscape = None

    def _exec(self, cmd: List[str], shell: bool=False, timeout: int=REQUEST_TIMEOUT) -> str:
        enhanced_log("DEBUG", "Executing command", {"cmd": " ".join(cmd)})
        try:
            result = w.worker(cmd).shell() if shell else w.worker(cmd).output()
            enhanced_log("DEBUG", "Command output size", {"chars": len(result)})
            return result
        except Exception as e:
            enhanced_log("ERROR", "Command failed", {"cmd": " ".join(cmd), "error": str(e)})
            return ""

    def get_results(self) -> List[Dict]:
        enhanced_log("INFO", "Processing channel", {"channel": self.channel})
        try:
            if 'extractaudio-' in self.channel:
                return self._handle_audio_extraction()
            if 'keyword' in self.channel:
                return self.get_keyword_videos()
            if 'list' in self.channel:
                return self._handle_playlist()
            return self._handle_regular_channel()
        except Exception as e:
            enhanced_log("ERROR", "get_results error", {"channel":self.channel,"error":str(e)})
            return []

    def _handle_audio_extraction(self):
        is_list = 'list-' in self.channel
        url_key = self.channel.replace('extractaudio-','')
        if is_list:
            url_key = url_key.replace('list-','')
            self.channel_url = f'https://www.youtube.com/playlist?list={url_key}'
        else:
            self.channel_url = url_key if 'www.youtube' in url_key else f'https://www.youtube.com/{url_key}'
        self._populate_channel_info()
        self.channel_description = f'Playlist {self.channel_name}' if is_list else self.get_channel_description()
        return self.get_list_audios() if is_list else self.get_channel_audios()

    def _handle_playlist(self):
        url_key = self.channel.replace('list-','')
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
        else:
            self.channel_name = self.get_channel_name()
            thumbs = self.get_channel_images()
            self.channel_poster = thumbs['poster']
            self.channel_landscape = thumbs['landscape']
            channel_cache[key] = {
                'name': self.channel_name,
                'poster': thumbs['poster'],
                'landscape': thumbs['landscape']
            }

    def get_list_videos(self):
        cmd = cmd_builder.build_info_extraction(
            self.channel_url,
            playlist_start=1,
            playlist_end=videos_limit
        )
        enhanced_log("INFO","Fetching playlist videos",{"url":self.channel_url})
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
        enhanced_log("INFO","Searching keyword",{"keyword":kw})
        return self._parse_results(self._exec(cmd))

    def get_channel_videos(self):
        cu = self.channel_url + ('/videos' if '/streams' not in self.channel_url else '')
        cmd = cmd_builder.build_info_extraction(
            cu,
            dateafter=f"today-{days_dateafter}days",
            playlist_start=1,
            playlist_end=videos_limit
        )
        return self._parse_results(self._exec(cmd))

    def get_channel_audios(self):
        cu = self.channel_url + ('/videos' if '/streams' not in self.channel_url else '')
        cmd = cmd_builder.build_info_extraction(
            cu,
            dateafter=f"today-{days_dateafter}days",
            playlist_start=1,
            playlist_end=videos_limit
        )
        return self._parse_results(self._exec(cmd), audio_mode=True)

    def get_list_audios(self):
        cmd = cmd_builder.build_info_extraction(
            self.channel_url,
            playlist_start=1,
            playlist_end=videos_limit
        )
        return self._parse_results(self._exec(cmd), audio_mode=True,
                                   playlist_id=self.channel_url.split('list=')[1])

    def _parse_results(self, out: str, audio_mode: bool=False,
                       playlist_id: Optional[str]=None) -> List[Dict]:
        vids, lines = [], out.splitlines()
        enhanced_log("INFO","Parsing video entries",{"count":len([l for l in lines if l.strip()])})
        for ln in lines:
            if not ln.strip(): continue
            try:
                data = json.loads(ln)
                vid = data.get('id')
                if audio_mode: vid += '-audio'
                vids.append({
                    'id': vid,
                    'title': data.get('title'),
                    'upload_date': data.get('upload_date'),
                    'thumbnail': data.get('thumbnail'),
                    'description': data.get('description',''),
                    'channel_id': playlist_id or data.get('channel_id'),
                    'uploader_id': sanitize(self.channel_name) if playlist_id else data.get('uploader_id')
                })
            except json.JSONDecodeError:
                enhanced_log("WARNING","JSON parse failed",{"line":ln[:80]})
        enhanced_log("INFO","Parsed videos",{"parsed":len(vids)})
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
        out = self._exec(cmd)
        return sanitize(out.strip().strip('"'))

    def get_channel_description(self) -> str:
        desc_file = f"{media_folder}/{sanitize(self.channel_name)}.description"
        
        if platform.system()=="Linux":
            cmd = cmd_builder.build_description_extraction(self.channel_url, desc_file)
            cmd.extend(['>', '/dev/null','2>&1','&&','cat',f'"{desc_file}"'])
        else:
            cmd = cmd_builder.build_description_extraction(self.channel_url, desc_file)
            cmd.extend(['>','nul','2>&1','&&','more',f'"{desc_file}"'])
        
        out = self._exec(cmd, shell=True)
        if not out:
            try:
                with open(desc_file,'r',encoding='utf-8') as rf:
                    out = rf.read()
            except: out = f"Channel: {self.channel_name}"
        try: os.remove(desc_file)
        except: pass
        return out

    def get_channel_images(self) -> Dict[str,str]:
        cmd = cmd_builder.build_thumbnail_list(self.channel_url)
        out = self._exec(cmd)
        lines = [' '.join(l.split()) for l in out.splitlines() if l.strip()]
        headers, thumbs = [], []
        for i,l in enumerate(lines):
            if '[' in l: continue
            parts = l.split(' ')
            if i==0:
                headers = parts
            else:
                if parts[0]=='ID': continue
                try:
                    thumbs.append(dict(zip(headers,parts)))
                except: pass
        poster = next((t['URL'] for t in thumbs if t.get('ID')=='avatar_uncropped'), '')
        banner = [t for t in thumbs if 'banner' in t.get('ID','')]
        landscape = banner[-1]['URL'] if banner else ''
        return {'poster':poster,'landscape':landscape}

def filter_and_modify_bandwidth(m3u8: str) -> str:
    lines = m3u8.splitlines()
    best_bw, best_info, best_url = 0, None, None
    media_lines, sd_line = [], ""
    for i,ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF:"):
            try:
                bw = int(ln.split("BANDWIDTH=")[1].split(",")[0])
                url = lines[i+1] if i+1<len(lines) else ""
                if bw>best_bw:
                    best_bw, best_info, best_url = bw, ln.replace(f"BANDWIDTH={bw}","BANDWIDTH=279001"), url
            except: enhanced_log("WARNING","Stream parse failed",{"line":ln})
        elif ln.startswith("#EXT-X-MEDIA:URI"):
            if '234' in ln:
                media_lines.append(ln)
            else:
                sd_line = ln
    if sd_line and not any('234' in m for m in media_lines):
        media_lines.append(sd_line)
    out = "#EXTM3U\n#EXT-X-INDEPENDENT-SEGMENTS\n"
    for ml in media_lines: out += ml+"\n"
    if best_info and best_url:
        out += best_info+"\n"+best_url+"\n"
    return out

def clean_text(txt: str) -> str:
    if not txt: return ""
    t = html.escape(txt)
    return re.sub(r'[^\w\s\[\]\(\)\-\_\'\"\/\.\:\;\,]','',t)

def video_id_exists_in_content(folder: str, vid: str) -> bool:
    for r,d,files in os.walk(folder):
        for fn in files:
            if fn.endswith(".strm"):
                try:
                    with open(os.path.join(r,fn),'r',encoding='utf-8') as f:
                        if vid in f.read(): return True
                except Exception as e:
                    enhanced_log("WARNING","File read error",{"file":fn,"error":str(e)})
    return False

def process_channel_videos(data):
    yt, videos, method = data
    if not videos:
        enhanced_log("INFO","No videos for channel",{"channel":yt.channel_name})
        return
    enhanced_log("INFO","Processing videos",{"count":len(videos),"channel":yt.channel_name})
    chan_nfo, chan_folder = False, False
    proc_count = 0
    for vid in videos:
        try:
            vid_id = vid['id']
            cid    = vid['channel_id']
            title  = vid['title']
            thumb  = vid['thumbnail']
            desc   = vid['description']
            try:
                dt = datetime.strptime(vid['upload_date'],'%Y%m%d')
                up_date = dt.strftime('%Y-%m-%d')
                yr = dt.year
            except:
                up_date = datetime.now().strftime('%Y-%m-%d')
                yr = datetime.now().year
            uploader = vid['uploader_id']
            folder   = f"{media_folder}/{sanitize(f'{uploader} [{cid}]')}"
            path     = f"{folder}/{sanitize(title)}.strm"
            content  = f"http://{host}:{port}/{source_platform}/{method}/{vid_id}"
            if video_id_exists_in_content(folder, vid_id):
                enhanced_log("DEBUG","Already exists",{"video":vid_id})
                continue
            with file_lock:
                if not chan_folder:
                    f.folders().make_clean_folder(folder, False, ytdlp2strm_cfg)
                    chan_folder = True
            if yt.channel_url:
                ch_land, ch_post, ch_desc = yt.channel_landscape, yt.channel_poster, yt.channel_description
            else:
                tmp = Youtube(f'https://www.youtube.com/channel/{cid}')
                tmp._populate_channel_info()
                ch_land, ch_post, ch_desc = tmp.channel_landscape, tmp.channel_poster, tmp.get_channel_description()
            with file_lock:
                if not chan_nfo:
                    n.nfo("tvshow", folder, {
                        "title": uploader,
                        "plot": ch_desc.replace('\n',' <br/>'),
                        "season":"1","episode":"-1",
                        "landscape":ch_land,"poster":ch_post,"studio":"Youtube"
                    }).make_nfo()
                    chan_nfo = True
            n.nfo("episode", folder, {
                "item_name": sanitize(title),
                "title": sanitize(title),
                "upload_date": up_date,
                "year": yr,
                "plot": desc.replace('\n',' <br/>\n '),
                "season":"1","episode":"",
                "preview":thumb
            }).make_nfo()
            if not os.path.isfile(path):
                with file_lock:
                    f.folders().write_file(path, content)
                proc_count += 1
        except Exception as e:
            enhanced_log("ERROR","Video processing error",{"video":vid.get('id'),"error":str(e)})
    enhanced_log("INFO","Processed new videos",{"count":proc_count,"channel":yt.channel_name})

def to_strm(method: str):
    enhanced_log("INFO","Starting STRM generation",{"method":method,"channels":len(channels)})
    data_list = []
    for ch in channels:
        yt = Youtube(ch)
        enhanced_log("INFO","Fetching data",{"channel":ch})
        vids = yt.get_results()
        enhanced_log("INFO","Channel summary",{
            "name":yt.channel_name,"url":yt.channel_url,
            "videos":len(vids),"poster":bool(yt.channel_poster),
            "landscape":bool(yt.channel_landscape)
        })
        if vids:
            data_list.append((yt, vids, method))
        else:
            enhanced_log("WARNING","No videos found",{"channel":ch})
    if data_list:
        enhanced_log("INFO","Processing threads",{"threads":len(data_list)})
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(process_channel_videos, d): d[0].channel_name for d in data_list}
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    fut.result()
                    enhanced_log("INFO","Completed channel",{"channel":name})
                except Exception as e:
                    enhanced_log("ERROR","Thread failure",{"channel":name,"error":str(e)})
    enhanced_log("INFO","STRM generation complete")

def direct(youtube_id: str, remote_addr: str):
    now, key = time.time(), f"{remote_addr}_{youtube_id}"
    if key not in recent_requests:
        enhanced_log("INFO","New request",{"ip":remote_addr,"video":youtube_id})
        recent_requests[key] = now
    
    if '-audio' not in youtube_id:
        # Video handling
        cmd = cmd_builder.build(
            '-j',
            '--extractor-args', 'youtube:player-client=default,web_safari',
            f'https://www.youtube.com/watch?v={youtube_id}'
        )
        enhanced_log("DEBUG","Fetching manifest info",{"cmd":" ".join(cmd)})
        try:
            info = json.loads(w.worker(cmd).output())
            m3u8 = next((f["manifest_url"] for f in info.get("formats",[]) if "manifest_url" in f), None)
            if not m3u8:
                enhanced_log("WARNING","No manifest, fallback SD")
                cmd = cmd_builder.build_url_extraction(
                    f'https://www.youtube.com/watch?v={youtube_id}',
                    'best'
                )
                sd_url = w.worker(cmd).output().strip()
                return redirect(sd_url,301)
            resp = requests.get(m3u8, timeout=REQUEST_TIMEOUT)
            if resp.status_code==200:
                filtered = filter_and_modify_bandwidth(resp.text)
                headers = {
                    'Content-Type':'application/vnd.apple.mpegurl',
                    'Content-Disposition':'inline; filename="playlist.m3u8"',
                    'Cache-Control':'no-cache','Pragma':'no-cache','Expires':'0'
                }
                return Response(filtered, mimetype='application/vnd.apple.mpegurl', headers=headers)
        except Exception as e:
            enhanced_log("ERROR","Video request error",{"video":youtube_id,"error":str(e)})
    else:
        # Audio handling
        s_id = youtube_id.split('-audio')[0]
        cmd = cmd_builder.build_url_extraction(
            f'https://www.youtube.com/watch?v={s_id}',
            'bestaudio'
        )
        enhanced_log("DEBUG","Fetching audio URL",{"cmd":" ".join(cmd)})
        try:
            url = w.worker(cmd).output().strip()
            enhanced_log("INFO","Redirect to audio URL",{"url":url})
            return redirect(url,301)
        except Exception as e:
            enhanced_log("ERROR","Audio direct failed",{"video":s_id,"error":str(e)})
            abort(404)
    
    enhanced_log("ERROR","Direct failed; no URL",{"video":youtube_id})
    return ("Manifest URL not found or failed to redirect.",404)

def bridge(youtube_id: str):
    s_id = youtube_id.split('-audio')[0]
    url  = f'https://www.youtube.com/watch?v={s_id}'
    enhanced_log("INFO","Bridge start",{"video":s_id})
    
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
        enhanced_log("DEBUG","Bridge cmd",{"cmd":" ".join(cmd)})
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        time.sleep(3)
        try:
            while True:
                chunk = proc.stdout.read(1024)
                if not chunk: break
                buf.append(chunk)
                if not sent and time.time()>start+3:
                    sent = True
                    for _ in range(len(buf)):
                        yield buf.pop(0)
                elif sent:
                    yield buf.pop(0)
                proc.poll()
        finally:
            proc.kill()
            enhanced_log("INFO","Bridge end",{"video":s_id})
    
    return Response(stream_with_context(gen()), mimetype="video/mp4")

def download(youtube_id: str):
    s_id = youtube_id.split('-audio')[0]
    temp = os.path.join(os.getcwd(),'temp')
    os.makedirs(temp, exist_ok=True)
    enhanced_log("INFO","Download start",{"video":s_id})
    
    # Build download command
    download_kwargs = {
        'format': 'bestaudio' if '-audio' in youtube_id else 'bv*+ba+ba.2',
        'output': os.path.join(temp,'%('+'title)s.%(ext)s')
    }
    if cfg.get("sponsorblock"):
        download_kwargs.update({
            'sponsorblock': True,
            'sponsorblock_cats': cfg.get('sponsorblock_cats', '')
        })
    
    cmd = cmd_builder.build_download(f'https://www.youtube.com/watch?v={s_id}', **download_kwargs)
    enhanced_log("DEBUG","Download cmd",{"cmd":" ".join(cmd)})
    
    try:
        w.worker(cmd).call()
        
        # Get filename
        fn_cmd = cmd_builder.build_metadata_extraction(
            f'https://www.youtube.com/watch?v={s_id}',
            'filename'
        )
        fname = w.worker(fn_cmd).output().strip()
        path = os.path.join(temp, fname)
        enhanced_log("INFO","Download complete",{"file":path})
        return send_file(path)
    except Exception as e:
        enhanced_log("ERROR","Download failed",{"video":s_id,"error":str(e)})
        abort(500, description="Download failed")