# plugins/youtube/routes.py

from flask import Blueprint, request, redirect, Response, send_file, abort, jsonify
from plugins.youtube.youtube import direct, bridge, download, serve_downloaded_file
import logging
import os

logger = logging.getLogger(__name__)

youtube_bp = Blueprint('youtube', __name__, url_prefix='/youtube')


@youtube_bp.route('/direct/<youtube_id>')
def youtube_direct(youtube_id):
    """
    Redirect to direct stream (video/audio) optimized,
    based on the `direct` method from the new YouTube module.
    Now also checks for downloaded files first.
    """
    logger.info(f"Direct request for video ID: {youtube_id} from {request.remote_addr}")
    try:
        # direct(id, remote_addr) → Response / redirect
        return direct(youtube_id, request.remote_addr)
    except Exception as e:
        logger.error(f"Error in direct streaming for {youtube_id}: {e}")
        abort(500, description=f"Streaming failed: {e}")


@youtube_bp.route('/bridge/<youtube_id>')
def youtube_bridge(youtube_id):
    """
    Bridge-type streaming (buffered), using the `bridge` method.
    Now also checks for downloaded files first.
    """
    logger.info(f"Bridge request for video ID: {youtube_id}")
    try:
        return bridge(youtube_id)
    except Exception as e:
        logger.error(f"Error in bridge streaming for {youtube_id}: {e}")
        abort(500, description=f"Bridge streaming failed: {e}")


@youtube_bp.route('/redirect/<youtube_id>')
def youtube_redirect(youtube_id):
    """
    Alias kept for v0: redirects exactly like `/direct`.
    """
    logger.info(f"Redirect request for video ID: {youtube_id}")
    try:
        return direct(youtube_id, request.remote_addr)
    except Exception as e:
        logger.error(f"Error in redirect for {youtube_id}: {e}")
        abort(500, description=f"Redirect failed: {e}")


@youtube_bp.route('/download/<youtube_id>')
def youtube_download(youtube_id):
    """
    Runs the `download` method, returning the video/audio file.
    """
    logger.info(f"Download request for video ID: {youtube_id}")
    try:
        return download(youtube_id)
    except Exception as e:
        logger.error(f"Error in download for {youtube_id}: {e}")
        abort(500, description=f"Download failed: {e}")


@youtube_bp.route('/serve/<youtube_id>')
def youtube_serve(youtube_id):
    """
    NEW: Serve downloaded video files directly from disk.
    This is more efficient than the download route for already downloaded files.
    """
    logger.info(f"Serve request for video ID: {youtube_id}")
    try:
        return serve_downloaded_file(youtube_id)
    except Exception as e:
        logger.error(f"Error serving file for {youtube_id}: {e}")
        abort(404, description=f"File not found: {e}")


@youtube_bp.route('/status/<youtube_id>')
def youtube_status(youtube_id):
    """
    NEW: Check if a video is available locally or needs to be streamed.
    Returns JSON with status information.
    """
    logger.info(f"Status check for video ID: {youtube_id}")
    try:
        from plugins.youtube.youtube import video_file_exists_in_downloads, download_folder

        downloaded_file = video_file_exists_in_downloads(download_folder, youtube_id)

        if downloaded_file:
            file_size = os.path.getsize(downloaded_file) if os.path.exists(downloaded_file) else 0
            return jsonify({
                'status': 'downloaded',
                'file_path': downloaded_file,
                'file_size': file_size,
                'available_locally': True
            })
        else:
            return jsonify({
                'status': 'streaming_only',
                'available_locally': False,
                'message': 'Video available via streaming only'
            })
    except Exception as e:
        logger.error(f"Error checking status for {youtube_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@youtube_bp.errorhandler(404)
def youtube_not_found(error):
    """Handle 404 errors specifically for YouTube routes"""
    return jsonify({
        'error': 'Video not found',
        'message': str(error.description)
    }), 404


@youtube_bp.errorhandler(500)
def youtube_internal_error(error):
    """Handle 500 errors specifically for YouTube routes"""
    return jsonify({
        'error': 'Internal server error',
        'message': str(error.description)
    }), 500