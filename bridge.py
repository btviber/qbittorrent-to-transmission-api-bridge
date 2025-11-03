#!/usr/bin/env python3
"""
qBittorrent WebUI API to Transmission RPC Translation Layer
"""

from flask import Flask, request, jsonify
import argparse

# Import our modules
from logging_utils import log_info, log_debug, log_error, set_verbosity
from qbittorrent_client import QBittorrentClient
from handlers import (
    set_qbt_client,
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

# Initialize qBittorrent client
qbt_client = QBittorrentClient(QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD)
set_qbt_client(qbt_client)


@app.route('/transmission/rpc', methods=['POST'])
def transmission_rpc():
    """Main Transmission RPC endpoint"""

    try:
        data = request.get_json()
        method = data.get('method', '')
        arguments = data.get('arguments', {})
        tag = data.get('tag')

        log_info(f"\n[RPC] ===== Incoming Request =====")
        log_info(f"[RPC] Method: {method}")
        log_debug(f"[RPC] Tag: {tag}")
        log_debug(f"[RPC] Arguments: {arguments}")

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
            return jsonify({
                'result': 'error',
                'tag': tag
            })

        log_debug(f"[RPC] Response: success")
        return jsonify({
            'arguments': result,
            'result': 'success',
            'tag': tag
        })

    except Exception as e:
        log_error(f"Exception during request handling: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'result': str(e),
            'tag': data.get('tag') if 'data' in locals() else None
        }), 500


def main():
    parser = argparse.ArgumentParser(
        description='qBittorrent to Transmission RPC Bridge',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Verbosity levels:
  (none)  - Errors and warnings only
  -v      - Show RPC operations (client actions)
  -vv     - Full debug (including qBittorrent API calls)
        '''
    )
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (-v for info, -vv for debug)')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=9091,
                       help='Port to listen on (default: 9091)')

    args = parser.parse_args()

    # Set global verbosity level
    verbosity = min(args.verbose, 2)  # Cap at level 2
    set_verbosity(verbosity)

    print("Starting qBittorrent to Transmission RPC Bridge")
    print(f"Verbosity level: {verbosity} {'(errors/warnings only)' if verbosity == 0 else '(info)' if verbosity == 1 else '(full debug)'}")
    print(f"Connecting to qBittorrent at: {QBITTORRENT_URL}")
    print(f"Listening on http://{args.host}:{args.port}/transmission/rpc")
    print()

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == '__main__':
    main()
