"""
RPC Method Handlers for Transmission to qBittorrent translation
"""

import base64
from typing import Dict, List
from qbittorrent_client import QBittorrentClient
from transmission_translator import TransmissionTranslator
from logging_utils import log_info, log_debug, log_warning, log_error


# Global client instance (will be set by bridge.py)
qbt_client: QBittorrentClient = None


def set_qbt_client(client: QBittorrentClient):
    """Set the global qBittorrent client instance"""
    global qbt_client
    qbt_client = client


def get_sorted_torrents() -> List[Dict]:
    """Get all torrents sorted by hash for consistent ID assignment"""
    torrents = qbt_client.get_torrents()
    return sorted(torrents, key=lambda t: t['hash'])


def handle_torrent_get(arguments: Dict) -> Dict:
    """Handle torrent-get method"""
    log_info(f"[RPC] torrent-get")
    log_debug(f"[RPC] Raw arguments IDs: {arguments.get('ids', 'not specified')}")
    fields = arguments.get('fields', [])

    # Get all torrents and sort by hash for consistent ordering
    sorted_torrents = get_sorted_torrents()

    ids = TransmissionTranslator.get_torrent_ids(arguments, sorted_torrents)

    log_debug(f"[RPC] Requested fields: {fields if fields else 'all'}")
    log_debug(f"[RPC] Requested IDs (after translation): {ids if ids else 'all'}")

    torrents = []

    for idx, qbt_torrent in enumerate(sorted_torrents):
        # ids is None means return all torrents
        # ids is non-empty list means return only matching torrents
        if ids is None or qbt_torrent['hash'] in ids:
            # Sequential ID is 1-based position in sorted list
            sequential_id = idx + 1
            transmission_torrent = TransmissionTranslator.qbt_to_transmission_torrent(
                qbt_torrent, qbt_client, sequential_id
            )

            # Debug: Log what ID we're sending to client
            log_debug(f"[RPC] Sending torrent to client: name='{qbt_torrent.get('name', 'unknown')}', hash={qbt_torrent['hash'][:8]}..., sequential_id={sequential_id}, literal_id={int(qbt_torrent['hash'][:8], 16)}")

            # Filter fields if specified
            if fields:
                transmission_torrent = {
                    k: v for k, v in transmission_torrent.items()
                    if k in fields
                }

            torrents.append(transmission_torrent)

    log_debug(f"[RPC] Returning {len(torrents)} torrent(s)")
    return {'torrents': torrents}


def handle_torrent_add(arguments: Dict) -> Dict:
    """Handle torrent-add method"""
    log_info(f"[RPC] torrent-add")
    kwargs = {}

    if 'filename' in arguments:
        kwargs['filename'] = arguments['filename']
        log_debug(f"[RPC] Adding from URL: {arguments['filename']}")

    if 'metainfo' in arguments:
        kwargs['torrent'] = base64.b64decode(arguments['metainfo'])
        log_debug(f"[RPC] Adding from metainfo (base64 decoded)")

    if 'download-dir' in arguments:
        kwargs['download_dir'] = arguments['download-dir']
        log_debug(f"[RPC] Download directory: {arguments['download-dir']}")

    if 'paused' in arguments:
        kwargs['paused'] = arguments['paused']
        log_debug(f"[RPC] Paused: {arguments['paused']}")

    success = qbt_client.add_torrent(**kwargs)

    if success:
        log_info(f"[RPC] Torrent added successfully")
        # Get the newly added torrent
        torrents = qbt_client.get_torrents()
        if torrents:
            newest_torrent = max(torrents, key=lambda x: x.get('added_on', 0))
            transmission_torrent = TransmissionTranslator.qbt_to_transmission_torrent(
                newest_torrent, qbt_client
            )
            return {'torrent-added': transmission_torrent}
    else:
        log_error(f"Failed to add torrent")

    return {}


def handle_torrent_start(arguments: Dict) -> Dict:
    """Handle torrent-start method"""
    log_info(f"[RPC] torrent-start")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    if ids:
        qbt_client.start_torrents(ids)
    else:
        log_warning("No valid torrent IDs provided for start")
    return {}


def handle_torrent_stop(arguments: Dict) -> Dict:
    """Handle torrent-stop method"""
    log_info(f"[RPC] torrent-stop")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    if ids:
        qbt_client.stop_torrents(ids)
    else:
        log_warning("No valid torrent IDs provided for stop")
    return {}


def handle_torrent_verify(arguments: Dict) -> Dict:
    """Handle torrent-verify method"""
    log_info(f"[RPC] torrent-verify")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    if ids:
        qbt_client.verify_torrents(ids)
    else:
        log_warning("No valid torrent IDs provided for verify")
    return {}


def handle_torrent_reannounce(arguments: Dict) -> Dict:
    """Handle torrent-reannounce method"""
    log_info(f"[RPC] torrent-reannounce")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    if ids:
        qbt_client.reannounce_torrents(ids)
    else:
        log_warning("No valid torrent IDs provided for reannounce")
    return {}


def handle_torrent_set(arguments: Dict) -> Dict:
    """Handle torrent-set method"""
    log_info(f"[RPC] torrent-set")
    log_debug(f"[RPC] Arguments: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())

    if not ids:
        log_warning("No valid torrent IDs provided for torrent-set")
        return {}

    # Handle tracker operations
    if 'trackerAdd' in arguments:
        trackers = arguments['trackerAdd']
        log_debug(f"[RPC] trackerAdd detected: {trackers}")
        for torrent_hash in ids:
            qbt_client.add_trackers(torrent_hash, trackers)

    if 'trackerRemove' in arguments:
        tracker_ids = arguments['trackerRemove']
        log_debug(f"[RPC] trackerRemove detected: {tracker_ids}")
        # In Transmission, trackerRemove contains tracker IDs (integers)
        for torrent_hash in ids:
            trackers = qbt_client.get_torrent_trackers(torrent_hash)
            urls_to_remove = []

            for tracker_id in tracker_ids:
                # Find tracker by ID (tier)
                for tracker in trackers:
                    if tracker.get('tier') == tracker_id and tracker.get('url'):
                        if tracker['url'] not in ['** [DHT] **', '** [PeX] **', '** [LSD] **']:
                            urls_to_remove.append(tracker['url'])
                            log_debug(f"[RPC] Will remove tracker ID {tracker_id}: {tracker['url']}")
                        break

            if urls_to_remove:
                qbt_client.remove_trackers(torrent_hash, urls_to_remove)

    if 'trackerReplace' in arguments:
        tracker_replace = arguments['trackerReplace']
        log_debug(f"[RPC] trackerReplace detected: {tracker_replace}")

        if not tracker_replace or len(tracker_replace) < 2:
            log_warning("Invalid trackerReplace format, expected [tracker_id, new_url]")
            return {}

        tracker_id = tracker_replace[0]
        new_url = tracker_replace[1]
        log_debug(f"[RPC] Replacing tracker ID {tracker_id} with: {new_url}")

        # Replace tracker for each torrent
        for torrent_hash in ids:
            trackers = qbt_client.get_torrent_trackers(torrent_hash)

            # Find the tracker by ID (tier)
            for tracker in trackers:
                if tracker.get('tier') == tracker_id and tracker.get('url'):
                    old_url = tracker['url']
                    if old_url not in ['** [DHT] **', '** [PeX] **', '** [LSD] **']:
                        log_debug(f"[RPC] Found tracker to replace: {old_url}")
                        qbt_client.edit_tracker(torrent_hash, old_url, new_url)
                    break

    # Handle file priority changes
    if 'files-unwanted' in arguments:
        file_indices = arguments['files-unwanted']
        log_debug(f"[RPC] files-unwanted detected: {file_indices}")
        for torrent_hash in ids:
            qbt_client.set_file_priority(torrent_hash, file_indices, 0)  # 0 = do not download

    if 'files-wanted' in arguments:
        file_indices = arguments['files-wanted']
        log_debug(f"[RPC] files-wanted detected: {file_indices}")
        for torrent_hash in ids:
            qbt_client.set_file_priority(torrent_hash, file_indices, 1)  # 1 = normal priority

    if 'priority-high' in arguments:
        file_indices = arguments['priority-high']
        log_debug(f"[RPC] priority-high detected: {file_indices}")
        for torrent_hash in ids:
            qbt_client.set_file_priority(torrent_hash, file_indices, 6)  # 6 = high priority

    if 'priority-low' in arguments:
        file_indices = arguments['priority-low']
        log_debug(f"[RPC] priority-low detected: {file_indices}")
        for torrent_hash in ids:
            qbt_client.set_file_priority(torrent_hash, file_indices, 1)  # 1 = normal (qBT doesn't have "low")

    if 'priority-normal' in arguments:
        file_indices = arguments['priority-normal']
        log_debug(f"[RPC] priority-normal detected: {file_indices}")
        for torrent_hash in ids:
            qbt_client.set_file_priority(torrent_hash, file_indices, 1)  # 1 = normal

    # Handle other torrent-set operations
    # TODO: Implement other settings like speed limits, peer limits, etc.

    return {}


def handle_torrent_remove(arguments: Dict) -> Dict:
    """Handle torrent-remove method"""
    log_info(f"[RPC] torrent-remove")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    delete_data = arguments.get('delete-local-data', False)
    log_debug(f"[RPC] Delete local data: {delete_data}")

    if ids:
        qbt_client.remove_torrents(ids, delete_data)
    else:
        log_warning("No valid torrent IDs provided for remove")
    return {}


def handle_torrent_set_location(arguments: Dict) -> Dict:
    """Handle torrent-set-location method"""
    log_info(f"[RPC] torrent-set-location")
    log_debug(f"[RPC] Arguments: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    location = arguments.get('location', '')
    move = arguments.get('move', True)  # Transmission default is True

    if not ids:
        log_warning("No torrent IDs provided for set-location")
        return {}

    if not location:
        log_warning("No location provided for set-location")
        return {}

    # Note: qBittorrent's setLocation always moves files
    # If move=False in Transmission, this is a mismatch in behavior
    if not move:
        log_warning("qBittorrent always moves files. 'move=false' not supported")

    qbt_client.set_torrent_location(ids, location)
    return {}


def handle_tracker_add(arguments: Dict) -> Dict:
    """Handle torrent-tracker-add method (Transmission: trackerAdd)"""
    log_info(f"[RPC] tracker-add")
    log_debug(f"[RPC] Arguments: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    trackers = arguments.get('trackerAdd', [])

    if not ids:
        log_warning("No torrent IDs provided for tracker-add")
        return {}

    if not trackers:
        log_warning("No trackers provided for tracker-add")
        return {}

    # Add trackers to each torrent
    for torrent_hash in ids:
        qbt_client.add_trackers(torrent_hash, trackers)

    return {}


def handle_tracker_remove(arguments: Dict) -> Dict:
    """Handle torrent-tracker-remove method (Transmission: trackerRemove)"""
    log_info(f"[RPC] tracker-remove")
    log_debug(f"[RPC] Arguments: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    tracker_ids = arguments.get('trackerRemove', [])

    if not ids:
        log_warning("No torrent IDs provided for tracker-remove")
        return {}

    if not tracker_ids:
        log_warning("No tracker IDs provided for tracker-remove")
        return {}

    # In Transmission, trackerRemove contains tracker IDs (integers)
    # We need to map these to tracker URLs from the torrent
    for torrent_hash in ids:
        trackers = qbt_client.get_torrent_trackers(torrent_hash)
        urls_to_remove = []

        for tracker_id in tracker_ids:
            # Find tracker by ID (tier)
            for tracker in trackers:
                if tracker.get('tier') == tracker_id and tracker.get('url'):
                    urls_to_remove.append(tracker['url'])
                    break

        if urls_to_remove:
            qbt_client.remove_trackers(torrent_hash, urls_to_remove)

    return {}


def handle_tracker_replace(arguments: Dict) -> Dict:
    """Handle torrent-tracker-replace method (Transmission: trackerReplace)"""
    log_info(f"[RPC] tracker-replace")
    log_debug(f"[RPC] Arguments: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    tracker_replace = arguments.get('trackerReplace', [])

    if not ids:
        log_warning("No torrent IDs provided for tracker-replace")
        return {}

    if not tracker_replace or len(tracker_replace) < 2:
        log_warning("Invalid trackerReplace format, expected [tracker_id, new_url]")
        return {}

    tracker_id = tracker_replace[0]
    new_url = tracker_replace[1]

    # Replace tracker for each torrent
    for torrent_hash in ids:
        trackers = qbt_client.get_torrent_trackers(torrent_hash)

        # Find the tracker by ID (tier)
        for tracker in trackers:
            if tracker.get('tier') == tracker_id and tracker.get('url'):
                old_url = tracker['url']
                qbt_client.edit_tracker(torrent_hash, old_url, new_url)
                break

    return {}


def handle_torrent_rename_path(arguments: Dict) -> Dict:
    """Handle torrent-rename-path method"""
    log_info(f"[RPC] torrent-rename-path")
    log_debug(f"[RPC] Arguments: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, get_sorted_torrents())
    path = arguments.get('path', '')
    name = arguments.get('name', '')

    if not ids:
        log_warning("No torrent IDs provided for rename-path")
        return {}

    if not name:
        log_warning("No new name provided for rename-path")
        return {}

    # In Transmission, 'path' is the current name, 'name' is the new name
    # We need to determine if we're renaming the torrent itself or a file within it
    for torrent_hash in ids:
        # Get torrent info to check if path matches the torrent name (root)
        qbt_torrents = qbt_client.get_torrents(torrent_hash)
        if not qbt_torrents:
            log_warning(f"Could not find torrent with hash {torrent_hash}")
            continue

        qbt_torrent = qbt_torrents[0]
        torrent_name = qbt_torrent.get('name', '')

        # Check if we're renaming the torrent itself
        # This happens when path matches the torrent name or is the root directory
        if path == torrent_name or not path or path == '.':
            # Rename the torrent itself
            log_debug(f"[RPC] Renaming torrent from '{torrent_name}' to '{name}'")
            qbt_client.rename_torrent(torrent_hash, name)
        else:
            # Rename a file/folder within the torrent
            log_debug(f"[RPC] Renaming file/folder '{path}' to '{name}'")
            qbt_client.rename_file(torrent_hash, path, name)

    return {'path': path, 'name': name}


def handle_session_get(arguments: Dict) -> Dict:
    """Handle session-get method"""
    return {
        'alt-speed-down': 0,
        'alt-speed-enabled': False,
        'alt-speed-time-begin': 0,
        'alt-speed-time-enabled': False,
        'alt-speed-time-end': 0,
        'alt-speed-time-day': 0,
        'alt-speed-up': 0,
        'blocklist-url': '',
        'blocklist-enabled': False,
        'blocklist-size': 0,
        'cache-size-mb': 4,
        'config-dir': '',
        'download-dir': '',
        'download-queue-size': 5,
        'download-queue-enabled': True,
        'dht-enabled': True,
        'encryption': 'preferred',
        'idle-seeding-limit': 30,
        'idle-seeding-limit-enabled': False,
        'incomplete-dir': '',
        'incomplete-dir-enabled': False,
        'lpd-enabled': False,
        'peer-limit-global': 200,
        'peer-limit-per-torrent': 50,
        'pex-enabled': True,
        'peer-port': 51413,
        'peer-port-random-on-start': False,
        'port-forwarding-enabled': True,
        'queue-stalled-enabled': True,
        'queue-stalled-minutes': 30,
        'rename-partial-files': True,
        'rpc-version': 15,
        'rpc-version-minimum': 1,
        'script-torrent-done-filename': '',
        'script-torrent-done-enabled': False,
        'seedRatioLimit': 2.0,
        'seedRatioLimited': False,
        'seed-queue-size': 10,
        'seed-queue-enabled': False,
        'speed-limit-down': 100,
        'speed-limit-down-enabled': False,
        'speed-limit-up': 100,
        'speed-limit-up-enabled': False,
        'start-added-torrents': True,
        'trash-original-torrent-files': False,
        'units': {
            'speed-units': ['KB/s', 'MB/s', 'GB/s'],
            'speed-bytes': 1000,
            'size-units': ['KB', 'MB', 'GB'],
            'size-bytes': 1000,
            'memory-units': ['KB', 'MB', 'GB'],
            'memory-bytes': 1024
        },
        'utp-enabled': True,
        'version': '4.0.6 (qBittorrent bridge)'
    }


def handle_session_stats(arguments: Dict) -> Dict:
    """Handle session-stats method"""
    log_info(f"[RPC] session-stats")

    # Get server state from qBittorrent (includes all-time and session stats)
    server_state = qbt_client.get_transfer_info()

    # Get all torrents to count active/paused/total
    torrents = qbt_client.get_torrents()

    active_count = 0
    paused_count = 0

    for torrent in torrents:
        state = torrent.get('state', '')
        if state in ['pausedDL', 'pausedUP']:
            paused_count += 1
        elif state in ['downloading', 'uploading', 'stalledDL', 'stalledUP', 'metaDL', 'queuedDL', 'queuedUP']:
            active_count += 1

    total_count = len(torrents)

    # Get current speeds
    download_speed = server_state.get('dl_info_speed', 0)
    upload_speed = server_state.get('up_info_speed', 0)

    # Get session statistics
    session_downloaded = server_state.get('dl_info_data', 0)
    session_uploaded = server_state.get('up_info_data', 0)

    # Get all-time statistics
    alltime_downloaded = server_state.get('alltime_dl', 0)
    alltime_uploaded = server_state.get('alltime_ul', 0)

    log_debug(f"[RPC] Stats - Active: {active_count}, Paused: {paused_count}, Total: {total_count}")
    log_debug(f"[RPC] Session: DL={session_downloaded} bytes, UL={session_uploaded} bytes")
    log_debug(f"[RPC] All-time: DL={alltime_downloaded} bytes, UL={alltime_uploaded} bytes")

    return {
        'activeTorrentCount': active_count,
        'downloadSpeed': download_speed,
        'pausedTorrentCount': paused_count,
        'torrentCount': total_count,
        'uploadSpeed': upload_speed,
        'cumulative-stats': {
            'downloadedBytes': alltime_downloaded,
            'filesAdded': 0,  # qBittorrent doesn't track this
            'secondsActive': 0,  # qBittorrent doesn't track this
            'sessionCount': 1,  # qBittorrent doesn't track this
            'uploadedBytes': alltime_uploaded
        },
        'current-stats': {
            'downloadedBytes': session_downloaded,
            'filesAdded': total_count,
            'secondsActive': 0,  # qBittorrent doesn't track this
            'sessionCount': 1,  # Current session
            'uploadedBytes': session_uploaded
        }
    }


def handle_free_space(arguments: Dict) -> Dict:
    """Handle free-space method"""
    log_info(f"[RPC] free-space")
    path = arguments.get('path', '')
    log_debug(f"[RPC] Requested path: {path}")

    # Get server state which includes free_space_on_disk
    server_state = qbt_client.get_transfer_info()
    free_space = server_state.get('free_space_on_disk', 0)

    log_debug(f"[RPC] Free space: {free_space} bytes")

    return {
        'path': path,
        'size-bytes': free_space
    }
