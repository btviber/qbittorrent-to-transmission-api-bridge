#!/usr/bin/env python3
"""
qBittorrent WebUI API to Transmission RPC Translation Layer
"""

from flask import Flask, request, jsonify
import argparse

# Import our modules
from logging_utils import log_info, log_debug, log_error, log_warning, log_trace, set_verbosity
from qbittorrent_client import QBittorrentClient
from sync_manager import SyncManager
from handlers import (
    set_qbt_client,
    set_sync_manager,
    handle_torrent_get,
    handle_torrent_add,
    handle_torrent_start,
    handle_torrent_stop,
    handle_torrent_verify,
    handle_torrent_reannounce,
    handle_torrent_set,
    handle_torrent_remove,
    handle_torrent_set_location,
    handle_tracker_add,
    handle_tracker_remove,
    handle_tracker_replace,
    handle_torrent_rename_path,
    handle_session_get,
    handle_session_stats,
    handle_free_space
)

app = Flask(__name__)

# Configuration
QBITTORRENT_URL = "http://localhost:8080"
QBITTORRENT_USERNAME = "admin"
QBITTORRENT_PASSWORD = "password"

# Authentication (set from command line args)
AUTH_USERNAME = None
AUTH_PASSWORD = None

# Initialize qBittorrent client and sync manager
qbt_client = QBittorrentClient(QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD)
sync_manager = SyncManager(qbt_client, poll_interval=1.5)
set_qbt_client(qbt_client)
set_sync_manager(sync_manager)


def check_authentication():
    """Check HTTP Basic Authentication if credentials are configured"""
    if AUTH_USERNAME is None or AUTH_PASSWORD is None:
        # No authentication required
        return True

    auth = request.authorization
    if not auth:
        return False

    return auth.username == AUTH_USERNAME and auth.password == AUTH_PASSWORD


@app.route('/transmission/rpc', methods=['POST'], strict_slashes=False)
def transmission_rpc():
    """Main Transmission RPC endpoint"""

    # Check authentication
    if not check_authentication():
        log_warning("[AUTH] Authentication failed")
        return jsonify({'result': 'error', 'error': 'Unauthorized'}), 401, {
            'WWW-Authenticate': 'Basic realm="Transmission RPC"'
        }

    try:
        # Force JSON parsing even if Content-Type header is not set correctly
        data = request.get_json(force=True)
        method = data.get('method', '')
        arguments = data.get('arguments', {})
        tag = data.get('tag')

        log_info(f"\n[RPC] ===== Incoming Request =====")
        log_info(f"[RPC] Method: {method}")
        log_trace(f"[RPC] Tag: {tag}")
        log_trace(f"[RPC] Arguments: {arguments}")

        result = None

        # Handle different RPC methods
        if method == 'torrent-get':
            result = handle_torrent_get(arguments)

        elif method == 'torrent-add':
            result = handle_torrent_add(arguments)

        elif method == 'torrent-start':
            result = handle_torrent_start(arguments)

        elif method == 'torrent-start-now':
            result = handle_torrent_start(arguments)

        elif method == 'torrent-stop':
            result = handle_torrent_stop(arguments)

        elif method == 'torrent-verify':
            result = handle_torrent_verify(arguments)

        elif method == 'torrent-reannounce':
            result = handle_torrent_reannounce(arguments)

        elif method == 'torrent-set':
            result = handle_torrent_set(arguments)

        elif method == 'torrent-remove':
            result = handle_torrent_remove(arguments)

        elif method == 'torrent-set-location':
            result = handle_torrent_set_location(arguments)

        elif method == 'torrent-tracker-add':
            result = handle_tracker_add(arguments)

        elif method == 'torrent-tracker-remove':
            result = handle_tracker_remove(arguments)

        elif method == 'torrent-tracker-replace':
            result = handle_tracker_replace(arguments)

        elif method == 'torrent-rename-path':
            result = handle_torrent_rename_path(arguments)

        elif method == 'session-get':
            result = handle_session_get(arguments)

        elif method == 'session-stats':
            result = handle_session_stats(arguments)

        elif method == 'free-space':
            result = handle_free_space(arguments)

        else:
            log_error(f"Unknown method '{method}'")
            response = {'result': 'error'}
            if tag is not None:
                response['tag'] = tag
            return jsonify(response)

        log_debug(f"[RPC] Response: success")
        response = {
            'arguments': result,
            'result': 'success'
        }
        # Only include tag if it was provided (match real Transmission behavior)
        if tag is not None:
            response['tag'] = tag
        return jsonify(response)

    except Exception as e:
        log_error(f"Exception during request handling: {e}")
        import traceback
        traceback.print_exc()
        response = {'result': str(e)}
        tag = data.get('tag') if 'data' in locals() else None
        if tag is not None:
            response['tag'] = tag
        return jsonify(response), 500


def main():
    parser = argparse.ArgumentParser(
        description='qBittorrent to Transmission RPC Bridge',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Verbosity levels:
  (none)  - Errors and warnings only
  -v      - Show RPC operations (client actions)
  -vv     - Show cache hits/misses, API calls
  -vvv    - Show everything (sync changes, arguments, all details)
        '''
    )
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (-v for info, -vv for debug, -vvv for trace)')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=9091,
                       help='Port to listen on (default: 9091)')
    parser.add_argument('--username', default=None,
                       help='Username for authentication (optional)')
    parser.add_argument('--password', default=None,
                       help='Password for authentication (optional)')

    args = parser.parse_args()

    # Set global authentication
    global AUTH_USERNAME, AUTH_PASSWORD
    AUTH_USERNAME = args.username
    AUTH_PASSWORD = args.password

    # Set global verbosity level
    verbosity = min(args.verbose, 3)  # Cap at level 3
    set_verbosity(verbosity)

    print("Starting qBittorrent to Transmission RPC Bridge")
    verbosity_names = {0: '(errors/warnings only)', 1: '(info)', 2: '(debug)', 3: '(trace)'}
    print(f"Verbosity level: {verbosity} {verbosity_names.get(verbosity, '(unknown)')}")
    print(f"Connecting to qBittorrent at: {QBITTORRENT_URL}")
    print(f"Starting background sync (polling every {sync_manager.poll_interval}s)...")
    if AUTH_USERNAME and AUTH_PASSWORD:
        print(f"Authentication: enabled (user: {AUTH_USERNAME})")
    else:
        print("Authentication: disabled")
    print(f"Listening on http://{args.host}:{args.port}/transmission/rpc")
    print()

    # Start background sync
    sync_manager.start()

    try:
        app.run(host=args.host, port=args.port, debug=False)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        sync_manager.stop()


if __name__ == '__main__':
    main()
