#!/usr/bin/env python3
"""
YouTube Playback Debug Tool
Tests the entire playback chain step by step
"""

import subprocess
import json
import requests
import time
import sys
import os
import re
from urllib.parse import urlparse
from pathlib import Path

def test_basic_connectivity():
    """Test basic internet and YouTube connectivity"""
    print("=" * 60)
    print("TESTING BASIC CONNECTIVITY")
    print("=" * 60)
    
    # Test internet connectivity
    try:
        response = requests.get("https://www.google.com", timeout=10)
        if response.status_code == 200:
            print("✓ Internet connectivity: OK")
        else:
            print(f"✗ Internet connectivity: Failed ({response.status_code})")
            return False
    except Exception as e:
        print(f"✗ Internet connectivity: Failed ({e})")
        return False
    
    # Test YouTube connectivity
    try:
        response = requests.get("https://www.youtube.com", timeout=10)
        if response.status_code == 200:
            print("✓ YouTube connectivity: OK")
        else:
            print(f"✗ YouTube connectivity: Failed ({response.status_code})")
            return False
    except Exception as e:
        print(f"✗ YouTube connectivity: Failed ({e})")
        return False
    
    return True

def test_ytdlp_installation():
    """Test yt-dlp installation and version"""
    print("\n" + "=" * 60)
    print("TESTING YT-DLP INSTALLATION")
    print("=" * 60)
    
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✓ yt-dlp version: {version}")
            
            # Check if version is recent (optional)
            try:
                year = int(version.split('.')[0])
                if year >= 2024:
                    print("✓ yt-dlp version is recent")
                else:
                    print("⚠ yt-dlp version might be outdated")
            except:
                pass
            
            return True
        else:
            print(f"✗ yt-dlp not working: {result.stderr}")
            return False
    except FileNotFoundError:
        print("✗ yt-dlp not found. Please install it:")
        print("  pip install yt-dlp")
        return False
    except Exception as e:
        print(f"✗ yt-dlp test failed: {e}")
        return False

def test_cookie_setup():
    """Test cookie configuration"""
    print("\n" + "=" * 60)
    print("TESTING COOKIE SETUP")
    print("=" * 60)
    
    cookie_paths = [
        "/root/.config/google-chrome/Default/Cookies",
        "/root/.config/chromium/Default/Cookies",
        os.path.expanduser("~/.config/google-chrome/Default/Cookies"),
        os.path.expanduser("~/.config/chromium/Default/Cookies")
    ]
    
    cookies_found = False
    for path in cookie_paths:
        if os.path.exists(path):
            print(f"✓ Found cookies at: {path}")
            cookies_found = True
            
            # Test cookies with yt-dlp
            try:
                test_cmd = [
                    'yt-dlp', 
                    '--cookies-from-browser', 'chrome',
                    '--simulate',
                    '--quiet',
                    'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
                ]
                result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    print("✓ Cookies are working with yt-dlp")
                else:
                    print(f"⚠ Cookies found but not working: {result.stderr.strip()}")
            except Exception as e:
                print(f"⚠ Cookie test error: {e}")
            break
    
    if not cookies_found:
        print("✗ No cookies found")
        print("  Recommendations:")
        print("  1. Install Chrome: sudo apt install google-chrome-stable")
        print("  2. Run Chrome and visit YouTube")
        print("  3. Sign in and watch a few videos")
        print("  4. Make sure cookies are saved")
    
    return cookies_found

def test_video_info_extraction(video_id):
    """Test video information extraction"""
    print(f"\n" + "=" * 60)
    print(f"TESTING VIDEO INFO EXTRACTION: {video_id}")
    print("=" * 60)
    
    # Test without cookies first
    cmd_basic = [
        'yt-dlp',
        '-j',
        '--no-warnings',
        f'https://www.youtube.com/watch?v={video_id}'
    ]
    
    print("Testing without cookies...")
    try:
        result = subprocess.run(cmd_basic, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and result.stdout.strip():
            try:
                info = json.loads(result.stdout)
                print(f"✓ Basic info extraction successful")
                print(f"  Title: {info.get('title', 'N/A')}")
                print(f"  Duration: {info.get('duration', 'N/A')} seconds")
                print(f"  Uploader: {info.get('uploader', 'N/A')}")
                print(f"  Formats available: {len(info.get('formats', []))}")
                
                # Check for age restrictions
                if info.get('age_limit', 0) > 0:
                    print(f"⚠ Age restricted content (limit: {info.get('age_limit')})")
                
                return info
            except json.JSONDecodeError:
                print("✗ Invalid JSON response")
        else:
            print(f"✗ Basic extraction failed: {result.stderr.strip()}")
    except Exception as e:
        print(f"✗ Basic extraction error: {e}")
    
    # Test with cookies
    print("\nTesting with cookies...")
    cmd_cookies = [
        'yt-dlp',
        '-j',
        '--cookies-from-browser', 'chrome',
        '--no-warnings',
        f'https://www.youtube.com/watch?v={video_id}'
    ]
    
    try:
        result = subprocess.run(cmd_cookies, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and result.stdout.strip():
            try:
                info = json.loads(result.stdout)
                print(f"✓ Cookie-based extraction successful")
                print(f"  Additional formats with cookies: {len(info.get('formats', []))}")
                return info
            except json.JSONDecodeError:
                print("✗ Invalid JSON response with cookies")
        else:
            print(f"✗ Cookie-based extraction failed: {result.stderr.strip()}")
    except Exception as e:
        print(f"✗ Cookie-based extraction error: {e}")
    
    return None

def test_format_availability(video_info):
    """Test what formats are available"""
    print(f"\n" + "=" * 60)
    print("TESTING FORMAT AVAILABILITY")
    print("=" * 60)
    
    if not video_info or 'formats' not in video_info:
        print("✗ No video info available")
        return None
    
    formats = video_info['formats']
    print(f"Total formats found: {len(formats)}")
    
    # Categorize formats
    video_formats = []
    audio_formats = []
    manifest_formats = []
    
    for fmt in formats:
        if 'manifest_url' in fmt:
            manifest_formats.append(fmt)
        elif fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
            video_formats.append(fmt)  # Combined video+audio
        elif fmt.get('acodec') != 'none':
            audio_formats.append(fmt)  # Audio only
        elif fmt.get('vcodec') != 'none':
            video_formats.append(fmt)  # Video only
    
    print(f"Video formats: {len(video_formats)}")
    print(f"Audio formats: {len(audio_formats)}")  
    print(f"Manifest formats: {len(manifest_formats)}")
    
    # Show best formats
    if video_formats:
        best_video = max(video_formats, key=lambda x: x.get('height', 0) or 0)
        print(f"Best video: {best_video.get('format_id')} - {best_video.get('height')}p - {best_video.get('ext')}")
    
    if audio_formats:
        best_audio = max(audio_formats, key=lambda x: x.get('abr', 0) or 0)
        print(f"Best audio: {best_audio.get('format_id')} - {best_audio.get('abr')}kbps - {best_audio.get('ext')}")
    
    if manifest_formats:
        print(f"Manifest available: {manifest_formats[0].get('format_id')}")
        return manifest_formats[0]
    
    return best_video if video_formats else (best_audio if audio_formats else None)

def test_url_extraction(video_id, format_selector="best"):
    """Test URL extraction with different format selectors"""
    print(f"\n" + "=" * 60)
    print(f"TESTING URL EXTRACTION: {format_selector}")
    print("=" * 60)
    
    strategies = [
        (f'-f {format_selector}', 'Basic format selection'),
        (f'-f {format_selector} --cookies-from-browser chrome', 'With cookies'),
        ('-f best[ext=mp4]', 'MP4 format only'),
        ('-f bestvideo+bestaudio', 'Best video + audio'),
        ('-f best', 'Simple best format')
    ]
    
    for strategy, description in strategies:
        print(f"\nTrying: {description}")
        cmd = ['yt-dlp', '--get-url', '--no-warnings'] + strategy.split() + [f'https://www.youtube.com/watch?v={video_id}']
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if result.returncode == 0 and result.stdout.strip():
                urls = result.stdout.strip().split('\n')
                print(f"✓ Success: Got {len(urls)} URL(s)")
                for i, url in enumerate(urls[:2]):  # Show first 2 URLs
                    print(f"  URL {i+1}: {url[:100]}...")
                    
                    # Test if URL is accessible
                    try:
                        response = requests.head(url, timeout=10)
                        print(f"    Status: {response.status_code}")
                        if 'content-length' in response.headers:
                            size_mb = int(response.headers['content-length']) / (1024*1024)
                            print(f"    Size: {size_mb:.1f} MB")
                    except Exception as e:
                        print(f"    URL test failed: {e}")
                
                return urls[0] if urls else None
            else:
                print(f"✗ Failed: {result.stderr.strip()}")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    return None

def test_manifest_processing(video_id):
    """Test HLS manifest processing"""
    print(f"\n" + "=" * 60)
    print("TESTING MANIFEST PROCESSING")
    print("=" * 60)
    
    # Get video info with manifest
    cmd = [
        'yt-dlp',
        '-j',
        '--cookies-from-browser', 'chrome',
        '--extractor-args', 'youtube:player-client=default,web_safari',
        '--no-warnings',
        f'https://www.youtube.com/watch?v={video_id}'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"✗ Failed to get video info: {result.stderr}")
            return None
        
        info = json.loads(result.stdout)
        
        # Find manifest URL
        manifest_url = None
        for fmt in info.get('formats', []):
            if 'manifest_url' in fmt:
                manifest_url = fmt['manifest_url']
                break
        
        if not manifest_url:
            print("✗ No manifest URL found")
            return None
        
        print(f"✓ Found manifest URL: {manifest_url[:100]}...")
        
        # Download manifest
        response = requests.get(manifest_url, timeout=30)
        if response.status_code != 200:
            print(f"✗ Failed to download manifest: {response.status_code}")
            return None
        
        print(f"✓ Downloaded manifest ({len(response.text)} chars)")
        
        # Analyze manifest
        lines = response.text.splitlines()
        stream_lines = [l for l in lines if l.startswith('#EXT-X-STREAM-INF:')]
        media_lines = [l for l in lines if l.startswith('#EXT-X-MEDIA:')]
        
        print(f"  Stream entries: {len(stream_lines)}")
        print(f"  Media entries: {len(media_lines)}")
        
        # Extract bandwidth info
        bandwidths = []
        for line in stream_lines:
            if 'BANDWIDTH=' in line:
                try:
                    bw = int(line.split('BANDWIDTH=')[1].split(',')[0])
                    bandwidths.append(bw)
                except:
                    pass
        
        if bandwidths:
            print(f"  Bandwidths: {min(bandwidths)} - {max(bandwidths)} bps")
        
        return response.text
        
    except Exception as e:
        print(f"✗ Manifest processing error: {e}")
        return None

def test_stream_playability(url):
    """Test if a stream URL is actually playable"""
    print(f"\n" + "=" * 60)
    print("TESTING STREAM PLAYABILITY")
    print("=" * 60)
    
    if not url:
        print("✗ No URL to test")
        return False
    
    print(f"Testing URL: {url[:100]}...")
    
    try:
        # Test with HEAD request first
        response = requests.head(url, timeout=10)
        print(f"✓ HEAD request: {response.status_code}")
        
        if response.status_code == 200:
            headers = response.headers
            print(f"  Content-Type: {headers.get('content-type', 'N/A')}")
            print(f"  Content-Length: {headers.get('content-length', 'N/A')}")
            print(f"  Accept-Ranges: {headers.get('accept-ranges', 'N/A')}")
            
            # Test partial content
            try:
                range_response = requests.get(url, headers={'Range': 'bytes=0-1023'}, timeout=10)
                if range_response.status_code == 206:
                    print(f"✓ Range requests supported")
                    print(f"  First 50 bytes: {range_response.content[:50]}")
                    return True
                else:
                    print(f"⚠ Range requests not supported: {range_response.status_code}")
                    return True  # Still might be playable
            except Exception as e:
                print(f"⚠ Range test failed: {e}")
                return True  # Still might be playable
        else:
            print(f"✗ URL not accessible: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Playability test failed: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python playback_debug.py <youtube_video_id>")
        print("Example: python playback_debug.py dQw4w9WgXcQ")
        sys.exit(1)
    
    video_id = sys.argv[1].replace('-audio', '')  # Clean ID
    is_audio = '-audio' in sys.argv[1]
    
    print("YOUTUBE PLAYBACK DEBUG TOOL")
    print("=" * 60)
    print(f"Video ID: {video_id}")
    print(f"Audio mode: {is_audio}")
    
    # Step 1: Basic connectivity
    if not test_basic_connectivity():
        print("\n❌ BASIC CONNECTIVITY FAILED - Cannot proceed")
        return
    
    # Step 2: yt-dlp installation
    if not test_ytdlp_installation():
        print("\n❌ YT-DLP NOT WORKING - Cannot proceed")
        return
    
    # Step 3: Cookie setup
    cookies_ok = test_cookie_setup()
    
    # Step 4: Video info extraction
    video_info = test_video_info_extraction(video_id)
    if not video_info:
        print("\n❌ VIDEO INFO EXTRACTION FAILED")
        return
    
    # Step 5: Format availability
    best_format = test_format_availability(video_info)
    
    # Step 6: URL extraction
    format_selector = 'bestaudio' if is_audio else 'best'
    stream_url = test_url_extraction(video_id, format_selector)
    
    # Step 7: Manifest processing (for video)
    if not is_audio:
        manifest_content = test_manifest_processing(video_id)
    
    # Step 8: Stream playability
    if stream_url:
        playable = test_stream_playability(stream_url)
    
    # Summary
    print(f"\n" + "=" * 60)
    print("DEBUG SUMMARY")
    print("=" * 60)
    
    print(f"✓ Connectivity: OK")
    print(f"✓ yt-dlp: OK")
    print(f"{'✓' if cookies_ok else '✗'} Cookies: {'OK' if cookies_ok else 'MISSING'}")
    print(f"{'✓' if video_info else '✗'} Video Info: {'OK' if video_info else 'FAILED'}")
    print(f"{'✓' if best_format else '✗'} Formats: {'Available' if best_format else 'NONE'}")
    print(f"{'✓' if stream_url else '✗'} URL Extraction: {'OK' if stream_url else 'FAILED'}")
    
    if not is_audio:
        manifest_ok = 'manifest_content' in locals() and manifest_content
        print(f"{'✓' if manifest_ok else '✗'} Manifest: {'OK' if manifest_ok else 'FAILED'}")
    
    if 'playable' in locals():
        print(f"{'✓' if playable else '✗'} Playability: {'OK' if playable else 'FAILED'}")
    
    # Recommendations
    print(f"\nRECOMMENDATIONS:")
    if not cookies_ok:
        print("1. Set up Chrome cookies for age-restricted content")
    if not video_info:
        print("2. Check if video ID is valid and accessible")
    if video_info and not best_format:
        print("3. Video might be geo-blocked or require authentication")
    if stream_url and 'playable' in locals() and not playable:
        print("4. Stream URLs might be expired or have DRM protection")

if __name__ == "__main__":
    main()