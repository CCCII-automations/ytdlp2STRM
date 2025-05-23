#!/usr/bin/env python3
"""
YouTube Channel Debug Tool
Tests different approaches to fetch videos from a YouTube channel
"""

import subprocess
import json
import sys

def test_channel_formats(channel_identifier):
    """Test different URL formats for the channel"""
    
    formats_to_test = [
        f"https://www.youtube.com/{channel_identifier}",
        f"https://www.youtube.com/{channel_identifier}/videos",
        f"https://www.youtube.com/{channel_identifier}/streams",
        channel_identifier  # Raw identifier
    ]
    
    print(f"Testing channel: {channel_identifier}")
    print("=" * 60)
    
    for url_format in formats_to_test:
        print(f"\nTesting URL: {url_format}")
        print("-" * 40)
        
        # Test 1: Get channel info
        try:
            cmd_info = [
                'yt-dlp', 
                '--print', '%(channel)s - %(channel_id)s',
                '--playlist-items', '1',
                '--no-warnings',
                '--ignore-errors',
                url_format
            ]
            
            result = subprocess.run(cmd_info, capture_output=True, text=True, timeout=30)
            if result.stdout.strip():
                print(f"? Channel info: {result.stdout.strip()}")
            else:
                print(f"? No channel info found")
                if result.stderr:
                    print(f"  Error: {result.stderr.strip()}")
        except Exception as e:
            print(f"? Error getting channel info: {e}")
        
        # Test 2: Count available videos
        try:
            cmd_count = [
                'yt-dlp',
                '--flat-playlist',
                '--print', '%(title)s',
                '--playlist-end', '5',  # Limit to first 5 for testing
                '--no-warnings',
                '--ignore-errors',
                url_format
            ]
            
            result = subprocess.run(cmd_count, capture_output=True, text=True, timeout=60)
            video_count = len([line for line in result.stdout.split('\n') if line.strip()])
            
            if video_count > 0:
                print(f"? Found {video_count} videos (first 5)")
                # Show first few titles
                titles = [line.strip() for line in result.stdout.split('\n') if line.strip()][:3]
                for i, title in enumerate(titles, 1):
                    print(f"  {i}. {title}")
            else:
                print(f"? No videos found")
                if result.stderr:
                    print(f"  Error: {result.stderr.strip()}")
                    
        except Exception as e:
            print(f"? Error counting videos: {e}")
        
        # Test 3: Try with date filter (like your script does)
        try:
            cmd_date = [
                'yt-dlp',
                '--dateafter', 'today-30days',  # Last 30 days
                '--flat-playlist',
                '--print', '%(title)s',
                '--playlist-end', '3',
                '--no-warnings',
                '--ignore-errors',
                url_format
            ]
            
            result = subprocess.run(cmd_date, capture_output=True, text=True, timeout=60)
            recent_count = len([line for line in result.stdout.split('\n') if line.strip()])
            
            if recent_count > 0:
                print(f"? Found {recent_count} recent videos (last 30 days)")
            else:
                print(f"? No recent videos found (last 30 days)")
                
        except Exception as e:
            print(f"? Error with date filter: {e}")

def test_your_script_approach(channel_identifier):
    """Test the exact approach your script uses"""
    
    print(f"\n\nTesting YOUR SCRIPT's approach:")
    print("=" * 60)
    
    # Replicate your script's logic
    channel_url = channel_identifier
    if not 'www.youtube' in channel_identifier:
        channel_url = f'https://www.youtube.com/{channel_identifier}'
    
    # Your script adds /videos if /streams is not in the channel
    if not '/streams' in channel_identifier:
        cu = f'{channel_url}/videos'
    else:
        cu = channel_url
    
    print(f"Original input: {channel_identifier}")
    print(f"Processed URL: {cu}")
    
    # Your script's exact command
    command = [
        'yt-dlp', 
        '--compat-options', 'no-youtube-channel-redirect',
        '--compat-options', 'no-youtube-unavailable-videos',
        '--dateafter', 'today-7days',  # Using 7 days for testing
        '--playlist-start', '1', 
        '--playlist-end', '10',  # Reduced for testing
        '--no-warning',
        '--dump-json',
        cu
    ]
    
    print(f"Command: {' '.join(command)}")
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        
        if result.stdout.strip():
            videos = []
            for line in result.stdout.split('\n'):
                if line.strip():
                    try:
                        data = json.loads(line)
                        videos.append({
                            'id': data.get('id'),
                            'title': data.get('title'),
                            'upload_date': data.get('upload_date')
                        })
                    except json.JSONDecodeError:
                        continue
            
            print(f"? Your script approach found {len(videos)} videos")
            for i, video in enumerate(videos[:3], 1):
                print(f"  {i}. {video['title']} ({video['upload_date']})")
                
        else:
            print("? Your script approach found no videos")
            if result.stderr:
                print(f"Error output: {result.stderr}")
                
    except Exception as e:
        print(f"? Error with your script approach: {e}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_youtube.py <channel_identifier>")
        print("Example: python debug_youtube.py @GabeGabi")
        print("Example: python debug_youtube.py https://www.youtube.com/@GabeGabi")
        sys.exit(1)
    
    channel_identifier = sys.argv[1]
    
    # Test various formats
    test_channel_formats(channel_identifier)
    
    # Test your script's specific approach
    test_your_script_approach(channel_identifier)
    
    print(f"\n\nSUGGESTIONS:")
    print("1. Try removing the date filter (--dateafter) to see all videos")
    print("2. Check if the channel has any recent videos within your date range")
    print("3. Some channels may require different URL formats")
    print("4. Consider using --cookies-from-browser if the channel has restrictions")

if __name__ == "__main__":
    main()