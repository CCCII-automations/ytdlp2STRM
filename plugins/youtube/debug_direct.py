#!/usr/bin/env python3
"""
YouTube Direct Function Debug Tool
Tests the direct() function logic step by step
"""

import json
import sys
import subprocess
import requests
import time
import re
from urllib.parse import urlparse, parse_qs

def test_video_info_extraction(youtube_id):
    """Test the video info extraction part"""
    print(f"Testing video info extraction for: {youtube_id}")
    print("-" * 50)
    
    command = [
        'yt-dlp', 
        '-j',
        '--no-warnings',
        '--extractor-args', 'youtube:player-client=default,web_safari',
        f'https://www.youtube.com/watch?v={youtube_id}'
    ]
    
    print(f"Command: {' '.join(command)}")
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f"✗ Command failed with return code: {result.returncode}")
            print(f"Error: {result.stderr}")
            return None
            
        if not result.stdout.strip():
            print("✗ No output from yt-dlp")
            return None
            
        try:
            full_info_json = json.loads(result.stdout)
            print("✓ Successfully extracted video info")
            
            # Print basic video info
            print(f"Title: {full_info_json.get('title', 'N/A')}")
            print(f"Duration: {full_info_json.get('duration', 'N/A')} seconds")
            print(f"View count: {full_info_json.get('view_count', 'N/A')}")
            print(f"Upload date: {full_info_json.get('upload_date', 'N/A')}")
            
            return full_info_json
            
        except json.JSONDecodeError as e:
            print(f"✗ Failed to parse JSON: {e}")
            print(f"Raw output (first 500 chars): {result.stdout[:500]}")
            return None
            
    except subprocess.TimeoutExpired:
        print("✗ Command timed out")
        return None
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return None

def test_manifest_extraction(full_info_json):
    """Test manifest URL extraction from video info"""
    print(f"\nTesting manifest URL extraction...")
    print("-" * 50)
    
    if not full_info_json:
        print("✗ No video info to process")
        return None
    
    formats = full_info_json.get("formats", [])
    print(f"Total formats found: {len(formats)}")
    
    # Look for manifest URLs
    manifest_urls = []
    for i, fmt in enumerate(formats):
        if "manifest_url" in fmt:
            manifest_url = fmt["manifest_url"]
            manifest_urls.append({
                'index': i,
                'url': manifest_url,
                'format_id': fmt.get('format_id', 'unknown'),
                'ext': fmt.get('ext', 'unknown'),
                'protocol': fmt.get('protocol', 'unknown')
            })
    
    if manifest_urls:
        print(f"✓ Found {len(manifest_urls)} manifest URLs")
        for manifest in manifest_urls:
            print(f"  Format ID: {manifest['format_id']}, Ext: {manifest['ext']}, Protocol: {manifest['protocol']}")
            print(f"  URL: {manifest['url'][:100]}...")
        return manifest_urls[0]['url']  # Return the first one
    else:
        print("✗ No manifest URLs found")
        
        # Show available formats for debugging
        print("\nAvailable formats:")
        for i, fmt in enumerate(formats[:10]):  # Show first 10
            print(f"  {i}: ID={fmt.get('format_id')}, Ext={fmt.get('ext')}, "
                  f"Protocol={fmt.get('protocol')}, URL exists={bool(fmt.get('url'))}")
        
        return None

def test_manifest_download(manifest_url):
    """Test downloading and processing the manifest"""
    print(f"\nTesting manifest download...")
    print("-" * 50)
    
    if not manifest_url:
        print("✗ No manifest URL to test")
        return None
    
    try:
        print(f"Downloading manifest from: {manifest_url[:100]}...")
        response = requests.get(manifest_url, timeout=30)
        
        if response.status_code != 200:
            print(f"✗ HTTP error: {response.status_code}")
            return None
            
        m3u8_content = response.text
        print(f"✓ Downloaded manifest ({len(m3u8_content)} characters)")
        
        # Analyze the manifest
        lines = m3u8_content.splitlines()
        stream_info_lines = [line for line in lines if line.startswith("#EXT-X-STREAM-INF:")]
        media_lines = [line for line in lines if line.startswith("#EXT-X-MEDIA:")]
        
        print(f"Stream info lines: {len(stream_info_lines)}")
        print(f"Media lines: {len(media_lines)}")
        
        # Extract bandwidth info
        bandwidths = []
        for line in stream_info_lines:
            if "BANDWIDTH=" in line:
                try:
                    bandwidth = int(line.split("BANDWIDTH=")[1].split(",")[0])
                    bandwidths.append(bandwidth)
                except:
                    pass
        
        if bandwidths:
            print(f"Bandwidths found: {sorted(bandwidths)}")
            print(f"Highest bandwidth: {max(bandwidths)}")
        
        return m3u8_content
        
    except requests.RequestException as e:
        print(f"✗ Request error: {e}")
        return None
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return None

def test_manifest_filtering(m3u8_content):
    """Test the manifest filtering logic from your script"""
    print(f"\nTesting manifest filtering...")
    print("-" * 50)
    
    if not m3u8_content:
        print("✗ No manifest content to filter")
        return None
    
    # Replicate your filter_and_modify_bandwidth function
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
            if i + 1 < len(lines):
                url = lines[i + 1]
                try:
                    bandwidth = int(info.split("BANDWIDTH=")[1].split(",")[0])
                    print(f"Found stream: bandwidth={bandwidth}")
                    
                    if bandwidth > highest_bandwidth:
                        highest_bandwidth = bandwidth
                        best_video_info = info.replace(f"BANDWIDTH={bandwidth}", "BANDWIDTH=279001")
                        best_video_url = url
                        print(f"  → New best stream (bandwidth={bandwidth})")
                except Exception as e:
                    print(f"  → Error parsing bandwidth: {e}")
        
        if line.startswith("#EXT-X-MEDIA:URI"):
            if '234' in line:
                high_audio = True
                media_lines.append(line)
                print(f"Found high quality audio: {line[:50]}...")
            else:
                sd_audio = line
                print(f"Found standard audio: {line[:50]}...")

    if not high_audio and sd_audio:
        media_lines.append(sd_audio)
        print("Using standard audio (no high quality found)")

    # Create the final M3U8 content
    final_m3u8 = "#EXTM3U\n#EXT-X-INDEPENDENT-SEGMENTS\n"
    
    # Add all EXT-X-MEDIA lines
    for media_line in media_lines:
        final_m3u8 += f"{media_line}\n"

    if best_video_info and best_video_url:
        final_m3u8 += f"{best_video_info}\n{best_video_url}\n"
        print(f"✓ Created filtered manifest")
        print(f"Best video bandwidth: {highest_bandwidth} → 279001")
        print(f"Media lines included: {len(media_lines)}")
    else:
        print("✗ No suitable video stream found")
        return None

    return final_m3u8

def test_fallback_sd_url(youtube_id):
    """Test the SD fallback URL extraction"""
    print(f"\nTesting SD fallback URL extraction...")
    print("-" * 50)
    
    command = [
        'yt-dlp',
        '-f', 'best',
        '--get-url',
        '--no-warnings',
        f'https://www.youtube.com/watch?v={youtube_id}'
    ]
    
    print(f"Command: {' '.join(command)}")
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            sd_url = result.stdout.strip()
            print(f"✓ SD URL found: {sd_url}")
            
            # Test if the URL is accessible
            try:
                response = requests.head(sd_url, timeout=10)
                print(f"✓ SD URL is accessible (status: {response.status_code})")
                return sd_url
            except:
                print(f"⚠ SD URL found but might not be accessible")
                return sd_url
        else:
            print(f"✗ Failed to get SD URL")
            if result.stderr:
                print(f"Error: {result.stderr}")
            return None
            
    except Exception as e:
        print(f"✗ Error getting SD URL: {e}")
        return None

def test_audio_extraction(youtube_id):
    """Test audio URL extraction for audio requests"""
    print(f"\nTesting audio URL extraction...")
    print("-" * 50)
    
    s_youtube_id = youtube_id.replace('-audio', '')
    
    command = [
        'yt-dlp',
        '-f', 'bestaudio',
        '--get-url',
        '--no-warnings',
        f'https://www.youtube.com/watch?v={s_youtube_id}'
    ]
    
    print(f"Command: {' '.join(command)}")
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            audio_url = result.stdout.strip()
            print(f"✓ Audio URL found: {audio_url}")
            
            # Test if the URL is accessible
            try:
                response = requests.head(audio_url, timeout=10)
                print(f"✓ Audio URL is accessible (status: {response.status_code})")
                return audio_url
            except:
                print(f"⚠ Audio URL found but might not be accessible")
                return audio_url
        else:
            print(f"✗ Failed to get audio URL")
            if result.stderr:
                print(f"Error: {result.stderr}")
            return None
            
    except Exception as e:
        print(f"✗ Error getting audio URL: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python direct_debug.py <youtube_id> [test_type]")
        print("Examples:")
        print("  python direct_debug.py dQw4w9WgXcQ")
        print("  python direct_debug.py dQw4w9WgXcQ-audio")
        print("  python direct_debug.py dQw4w9WgXcQ video")
        print("  python direct_debug.py dQw4w9WgXcQ audio")
        print("  python direct_debug.py dQw4w9WgXcQ manifest")
        sys.exit(1)
    
    youtube_id = sys.argv[1]
    test_type = sys.argv[2] if len(sys.argv) > 2 else 'all'
    
    print(f"DEBUGGING DIRECT FUNCTION FOR: {youtube_id}")
    print("=" * 60)
    
    is_audio = '-audio' in youtube_id
    clean_id = youtube_id.replace('-audio', '')
    
    print(f"Video ID: {clean_id}")
    print(f"Is audio request: {is_audio}")
    print(f"Test type: {test_type}")
    
    if test_type in ['all', 'video'] and not is_audio:
        # Test video processing
        full_info = test_video_info_extraction(clean_id)
        
        if test_type in ['all', 'manifest']:
            manifest_url = test_manifest_extraction(full_info)
            m3u8_content = test_manifest_download(manifest_url)
            filtered_manifest = test_manifest_filtering(m3u8_content)
            
            if not filtered_manifest:
                print("\n" + "="*60)
                print("MANIFEST FAILED - TESTING SD FALLBACK")
                print("="*60)
                test_fallback_sd_url(clean_id)
    
    if test_type in ['all', 'audio'] or is_audio:
        # Test audio processing
        test_audio_extraction(youtube_id)
    
    print(f"\n" + "="*60)
    print("DEBUG COMPLETE")
    print("="*60)
    
    print("\nRECOMMENDATIONS:")
    print("1. If manifest extraction fails, check your cookies configuration")
    print("2. If bandwidth filtering fails, check the M3U8 format")
    print("3. If SD fallback fails, the video might be restricted")
    print("4. For audio issues, try different audio quality settings")

if __name__ == "__main__":
    main()