# plugins/youtube/routes.py

from flask import Blueprint, request, redirect, Response, send_file, abort
from plugins.youtube.youtube import direct, bridge, download
import logging

logger = logging.getLogger(__name__)

youtube_bp = Blueprint('youtube', __name__, url_prefix='/youtube')

@youtube_bp.route('/direct/<youtube_id>')
def youtube_direct(youtube_id):
    """
    Redirect la stream-ul direct (video/audio) optim,
    pe baza metodei `direct` din noul modul YouTube.
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
    Streaming tip "bridge" (buffered), folosind metoda `bridge`.
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
    Alias păstrat pentru v0: redirecționează exact ca `/direct`.
    """
    logger.info(f"Redirect request for video ID: {youtube_id}")
    return direct(youtube_id, request.remote_addr)

@youtube_bp.route('/download/<youtube_id>')
def youtube_download(youtube_id):
    """
    Rulează metoda `download`, returnând fișierul video/audio.
    """
    logger.info(f"Download request for video ID: {youtube_id}")
    try:
        return download(youtube_id)
    except Exception as e:
        logger.error(f"Error in download for {youtube_id}: {e}")
        # În caz de eroare neașteptată
        abort(500, description=f"Download failed: {e}")