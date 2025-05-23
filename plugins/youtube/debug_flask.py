#!/usr/bin/env python3
"""
Flask Endpoint Test Tool
Tests your Flask endpoint directly to simulate real playback requests
"""

import requests
import time
import sys
import json
from urllib.parse import urljoin

def test_flask_endpoint(host, port, video_id, endpoint_type="direct"):
    """Test your Flask endpoint directly"""
    print(f"=" * 60)
    print(f"TESTING FLASK ENDPOINT: {endpoint_type}")
    print(f"=" * 60)
    
    base_url = f"http://{host}:{port}"
    endpoint_url = f"{base_url}/youtube/{endpoint_type}/{video_id}"
    
    print(f"Testing URL: {endpoint_url}")
    
    # Test different request methods
    test_methods = [
        ('GET', 'Standard GET request'),
        ('HEAD', 'HEAD request (metadata only)'),
    ]
    
    for method, description in test_methods:
        print(f"\n{description}:")
        try:
            if method == 'GET':
                response = requests.get(endpoint_url, timeout=30, allow_redirects=False)
            else:
                response = requests.head(endpoint_url, timeout=30, allow_redirects=False)
            
            print(f"  Status Code: {response.status_code}")
            print(f"  Headers:")
            for key, value in response.headers.items():
                print(f"    {key}: {value}")
            
            if response.status_code == 301 or response.status_code == 302:
                redirect_url = response.headers.get('Location')
                print(f"  Redirect URL: {redirect_url}")
                
                # Test the redirect URL
                if redirect_url:
                    print(f"  Testing redirect URL...")
                    try:
                        redirect_response = requests.head(redirect_url, timeout=10)
                        print(f"    Redirect status: {redirect_response.status_code}")
                        if 'content-length' in redirect_response.headers:
                            size_mb = int(redirect_response.headers['content-length']) / (1024*1024)
                            print(f"    Content size: {size_mb:.1f} MB")
                    except Exception as e:
                        print(f"    Redirect test failed: {e}")
            
            elif response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                print(f"  Content-Type: {content_type}")
                
                if method == 'GET':
                    if 'application/vnd.apple.mpegurl' in content_type:
                        # M3U8 playlist
                        content = response.text
                        print(f"  M3U8 Content ({len(content)} chars):")
                        lines = content.split('\n')[:10]  # First 10 lines
                        for line in lines:
                            if line.strip():
                                print(f"    {line}")
                        
                        # Analyze M3U8
                        stream_lines = [l for l in content.split('\n') if l.startswith('#EXT-X-STREAM-INF:')]
                        print(f"  Stream entries: {len(stream_lines)}")
                        
                    elif 'video/' in content_type or 'audio/' in content_type:
                        # Direct media stream
                        print(f"  Direct stream detected")
                        if 'content-length' in response.headers:
                            size_mb = int(response.headers['content-length']) / (1024*1024)
                            print(f"  Content size: {size_mb:.1f} MB")
            
            elif response.status_code >= 400:
                print(f"  Error response:")
                if response.text:
                    print(f"    {response.text[:500]}")
            
            return response.status_code, response.headers, response.text if method == 'GET' else None
            
        except requests.exceptions.Timeout:
            print(f"  ✗ Request timed out")
            return None, None, None
        except requests.exceptions.ConnectionError:
            print(f"  ✗ Connection failed - is your server running?")
            return None, None, None
        except Exception as e:
            print(f"  ✗ Request failed: {e}")
            return None, None, None

def test_streaming_performance(host, port, video_id, duration=10):
    """Test streaming performance"""
    print(f"\n" + "=" * 60)
    print(f"TESTING STREAMING PERFORMANCE ({duration}s)")
    print(f"=" * 60)
    
    endpoint_url = f"http://{host}:{port}/youtube/direct/{video_id}"
    
    try:
        start_time = time.time()
        response = requests.get(endpoint_url, stream=True, timeout=30)
        
        if response.status_code == 200:
            print(f"✓ Stream started successfully")
            
            bytes_received = 0
            chunks_received = 0
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    bytes_received += len(chunk)
                    chunks_received += 1
                    
                    elapsed = time.time() - start_time
                    if elapsed >= duration:
                        break
                    
                    if chunks_received % 100 == 0:  # Progress update every 100 chunks
                        mb_received = bytes_received / (1024*1024)
                        rate_mbps = mb_received / elapsed
                        print(f"  Progress: {mb_received:.1f} MB in {elapsed:.1f}s ({rate_mbps:.2f} MB/s)")
            
            total_time = time.time() - start_time
            total_mb = bytes_received / (1024*1024)
            avg_rate = total_mb / total_time
            
            print(f"✓ Streaming test completed:")
            print(f"  Duration: {total_time:.1f} seconds")
            print(f"  Data received: {total_mb:.1f} MB")
            print(f"  Average rate: {avg_rate:.2f} MB/s")
            print(f"  Chunks received: {chunks_received}")
            
            return True
            
        elif response.status_code in [301, 302]:
            redirect_url = response.headers.get('Location')
            print(f"✓ Redirect to: {redirect_url}")
            
            # Test the redirect URL for streaming
            if redirect_url:
                print(f"Testing redirect URL for streaming...")
                redirect_response = requests.get(redirect_url, stream=True, timeout=30)
                
                if redirect_response.status_code == 200:
                    print(f"✓ Redirect stream works")
                    return True
                else:
                    print(f"✗ Redirect stream failed: {redirect_response.status_code}")
                    return False
        else:
            print(f"✗ Stream failed: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"✗ Streaming test failed: {e}")
        return False

def test_different_endpoints(host, port, video_id):
    """Test different endpoint types"""
    print(f"\n" + "=" * 60)
    print("TESTING DIFFERENT ENDPOINTS")
    print(f"=" * 60)
    
    endpoints = [
        ('direct', 'Direct streaming'),
        ('bridge', 'Bridge streaming'),
        ('download', 'Download endpoint')
    ]
    
    results = {}
    
    for endpoint, description in endpoints:
        print(f"\nTesting {description}:")
        status, headers, content = test_flask_endpoint(host, port, video_id, endpoint)
        results[endpoint] = {
            'status': status,
            'headers': headers,
            'working': status is not None and status < 400
        }
        
        if status:
            print(f"  Result: {'✓ Working' if status < 400 else '✗ Failed'}")
        else:
            print(f"  Result: ✗ No response")
    
    return results

def simulate_player_requests(host, port, video_id):
    """Simulate how a media player would request the stream"""
    print(f"\n" + "=" * 60)
    print("SIMULATING MEDIA PLAYER REQUESTS")
    print(f"=" * 60)
    
    endpoint_url = f"http://{host}:{port}/youtube/direct/{video_id}"
    
    # Step 1: Initial request (like a player checking the stream)
    print("Step 1: Initial stream check...")
    try:
        response = requests.head(endpoint_url, timeout=10)
        print(f"  Status: {response.status_code}")
        
        if response.status_code in [301, 302]:
            actual_url = response.headers.get('Location')
            print(f"  Redirected to: {actual_url[:100]}...")
            
            # Step 2: Check the actual stream URL
            print("Step 2: Checking actual stream URL...")
            actual_response = requests.head(actual_url, timeout=10)
            print(f"  Actual URL status: {actual_response.status_code}")
            
            if actual_response.status_code == 200:
                print("  ✓ Stream URL is accessible")
                
                # Step 3: Test range requests (important for media players)
                print("Step 3: Testing range requests...")
                range_headers = {'Range': 'bytes=0-1023'}
                range_response = requests.get(actual_url, headers=range_headers, timeout=10)
                
                if range_response.status_code == 206:
                    print("  ✓ Range requests supported")
                    print(f"  Content-Range: {range_response.headers.get('content-range', 'N/A')}")
                else:
                    print(f"  ⚠ Range requests not supported: {range_response.status_code}")
                
                return True
            else:
                print(f"  ✗ Actual URL failed: {actual_response.status_code}")
                return False
        
        elif response.status_code == 200:
            print("  ✓ Direct stream (no redirect)")
            return True
        else:
            print(f"  ✗ Initial request failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ✗ Player simulation failed: {e}")
        return False

def main():
    if len(sys.argv) < 4:
        print("Usage: python flask_endpoint_test.py <host> <port> <video_id> [test_type]")
        print("Examples:")
        print("  python flask_endpoint_test.py localhost 5000 dQw4w9WgXcQ")
        print("  python flask_endpoint_test.py localhost 5000 dQw4w9WgXcQ-audio")
        print("  python flask_endpoint_test.py localhost 5000 dQw4w9WgXcQ all")
        print("  python flask_endpoint_test.py localhost 5000 dQw4w9WgXcQ performance")
        sys.exit(1)
    
    host = sys.argv[1]
    port = sys.argv[2]
    video_id = sys.argv[3]
    test_type = sys.argv[4] if len(sys.argv) > 4 else 'basic'
    
    print("FLASK ENDPOINT DEBUG TOOL")
    print("=" * 60)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Video ID: {video_id}")
    print(f"Test Type: {test_type}")
    
    # Test server connectivity first
    print(f"\nTesting server connectivity...")
    try:
        response = requests.get(f"http://{host}:{port}/", timeout=5)
        print(f"✓ Server is responding")
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to server at {host}:{port}")
        print(f"  Make sure your Flask application is running")
        return
    except Exception as e:
        print(f"⚠ Server test inconclusive: {e}")
    
    if test_type in ['basic', 'all']:
        # Test basic endpoint functionality
        status, headers, content = test_flask_endpoint(host, port, video_id, 'direct')
        
        if status is None:
            print(f"\n❌ ENDPOINT TEST FAILED - Server not responding")
            return
        elif status >= 400:
            print(f"\n❌ ENDPOINT ERROR - Status {status}")
            if content:
                print(f"Error message: {content}")
            return
        else:
            print(f"\n✓ ENDPOINT RESPONDING - Status {status}")
    
    if test_type in ['all', 'endpoints']:
        # Test all endpoint types
        results = test_different_endpoints(host, port, video_id)
        
        working_endpoints = [k for k, v in results.items() if v['working']]
        print(f"\nWorking endpoints: {', '.join(working_endpoints) if working_endpoints else 'None'}")
    
    if test_type in ['all', 'player']:
        # Simulate media player behavior
        player_success = simulate_player_requests(host, port, video_id)
        print(f"\nMedia player compatibility: {'✓ Good' if player_success else '✗ Issues detected'}")
    
    if test_type in ['all', 'performance']:
        # Test streaming performance
        streaming_success = test_streaming_performance(host, port, video_id, duration=5)
        print(f"\nStreaming performance: {'✓ Good' if streaming_success else '✗ Issues detected'}")
    
    # Final summary and recommendations
    print(f"\n" + "=" * 60)
    print("SUMMARY AND RECOMMENDATIONS")
    print("=" * 60)
    
    if 'status' in locals() and status:
        if status == 200:
            print("✓ Direct streaming (M3U8 or direct media)")
            print("  - Good for HLS-compatible players")
            print("  - Check M3U8 content for quality")
        elif status in [301, 302]:
            print("✓ Redirect-based streaming")
            print("  - Good for most players")
            print("  - Verify redirect URLs are accessible")
        elif status == 404:
            print("✗ Video not found")
            print("  - Check video ID validity")
            print("  - Verify video is accessible from your region")
        elif status == 403:
            print("✗ Access forbidden")
            print("  - Age-restricted content needs cookies")
            print("  - Configure Chrome cookies properly")
        else:
            print(f"⚠ Unexpected status: {status}")
    
    print(f"\nDebugging tips:")
    print(f"1. Check server logs for error details")
    print(f"2. Test with a known working video ID (e.g., dQw4w9WgXcQ)")
    print(f"3. Verify yt-dlp works independently:")
    print(f"   yt-dlp --get-url 'https://www.youtube.com/watch?v={video_id.replace('-audio', '')}'")
    print(f"4. Check your cookies configuration")
    print(f"5. Try different endpoint types (direct/bridge/download)")

if __name__ == "__main__":
    main()