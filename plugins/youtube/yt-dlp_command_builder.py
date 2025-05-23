#!/usr/bin/env python

import subprocess
import sys
import platform

def ask_input(prompt, default=None):
    response = input(f"{prompt} [{'default: ' + str(default) if default else 'required'}]: ").strip()
    return response if response else default

def get_formats(media_id):
    print("\nFetching format list from YouTube...")
    try:
        result = subprocess.run(
            ["yt-dlp", "-F", f"https://www.youtube.com/watch?v={media_id}"],
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("Error fetching formats:")
        print(e.stderr)
        sys.exit(1)

def build_command(media_id, media_type, ext, quality):
    base_url = f"https://www.youtube.com/watch?v={media_id}"
    command = ["yt-dlp"]

    if media_type == "1":  # Music
        command += [
            "-f", quality,
            "-x", "--audio-format", ext,
            base_url
        ]
    else:  # Video
        command += [
            "-f", quality,
            "-o", f"%(title)s.%(ext)s",
            base_url
        ]
    
    return command

def print_copy_command(command):
    command_str = " ".join(f'"{arg}"' if ' ' in arg else arg for arg in command)
    if platform.system() == "Windows":
        print("\nPowerShell command:\n")
        print(command_str)
    else:
        print("\nDebian terminal command:\n")
        print(command_str)

def main():
    print("=== YouTube Media Downloader CLI (yt-dlp wrapper) ===")

    media_id = ask_input("Enter the YouTube media ID")
    if not media_id:
        print("Media ID is required.")
        sys.exit(1)

    media_type = ask_input("Is it music or video? 1/music, 2/video", "1")

    get_formats(media_id)

    ext = ask_input("Enter the file extension you want to download (e.g., mp3, mp4, webm)", "mp3" if media_type == "1" else "mp4")
    quality = ask_input("Select the format code (from list above, e.g., 140 or 22)")

    if not quality:
        print("Quality/format code is required.")
        sys.exit(1)

    command = build_command(media_id, media_type, ext, quality)
    print_copy_command(command)

if __name__ == "__main__":
    main()
