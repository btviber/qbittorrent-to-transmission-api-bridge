"""
Transmission RPC to qBittorrent API Translation
"""

from typing import Dict, List, Optional
from qbittorrent_client import QBittorrentClient
from logging_utils import log_warning, log_error, log_debug


class TransmissionTranslator:
    """Translate between Transmission RPC and qBittorrent API"""

    # State mapping
    STATE_MAP = {
        'downloading': 4,      # Transmission: downloading
        'stalledDL': 4,
        'metaDL': 4,
        'pausedDL': 0,        # Transmission: stopped
        'queuedDL': 3,        # Transmission: queued
        'uploading': 6,       # Transmission: seeding
        'stalledUP': 6,
        'pausedUP': 0,
        'queuedUP': 3,
        'checkingUP': 2,      # Transmission: checking
        'checkingDL': 2,
        'checkingResumeData': 2,
        'error': 0,
        'missingFiles': 0,
        'unknown': 0,
    }

    @staticmethod
    def qbt_to_transmission_torrent(qbt_torrent: Dict, qbt_client: QBittorrentClient, sequential_id: int,
                                     requested_fields: List[str] = None, sync_manager=None) -> Dict:
        """Convert qBittorrent torrent to Transmission format

        Args:
            qbt_torrent: Torrent data from sync API (contains most fields)
            qbt_client: Client for fetching additional data if needed (deprecated, use sync_manager)
            sequential_id: Sequential torrent ID (1, 2, 3, ...)
            requested_fields: List of fields requested by client (None = all fields)
            sync_manager: Sync manager for cached detail fetching
        """

        torrent_hash = qbt_torrent['hash']

        # Check what additional data we need based on requested fields
        need_files = requested_fields is None or any(f in requested_fields for f in ['files', 'fileStats', 'priorities', 'wanted'])
        need_trackers = requested_fields is None or 'trackerStats' in requested_fields or 'trackers' in requested_fields
        need_properties = requested_fields is None or any(f in requested_fields for f in ['creator', 'dateCreated', 'comment', 'pieceCount', 'pieceSize'])

        # Get cached details if sync_manager is available, otherwise fallback to direct API
        if sync_manager:
            details = sync_manager.get_torrent_details(
                torrent_hash,
                need_files=need_files,
                need_trackers=need_trackers,
                need_properties=need_properties
            )
            files = details['files']
            trackers = details['trackers']
            properties = details['properties']
        else:
            # Fallback to direct API calls (for backward compatibility)
            properties = qbt_client.get_torrent_properties(torrent_hash) if need_properties else {}
            trackers = qbt_client.get_torrent_trackers(torrent_hash) if need_trackers else []
            files = qbt_client.get_torrent_files(torrent_hash) if need_files else []

        if files:
            log_debug(f"[FILES] Torrent {qbt_torrent.get('name', 'unknown')} (hash: {torrent_hash[:8]}...) returned {len(files)} file(s)")

        # Calculate rates
        download_rate = qbt_torrent.get('dlspeed', 0)
        upload_rate = qbt_torrent.get('upspeed', 0)

        # Calculate ratios
        downloaded = qbt_torrent.get('downloaded', 0)
        uploaded = qbt_torrent.get('uploaded', 0)
        ratio = uploaded / downloaded if downloaded > 0 else 0

        # Get status
        status = TransmissionTranslator.STATE_MAP.get(qbt_torrent.get('state', 'unknown'), 0)

        # Format trackers
        tracker_list = []
        tracker_stats = []
        for tracker in trackers:
            if tracker.get('url') and tracker['url'] not in ['** [DHT] **', '** [PeX] **', '** [LSD] **']:
                tracker_list.append({
                    'announce': tracker['url'],
                    'id': tracker.get('tier', 0),
                    'scrape': '',
                    'tier': tracker.get('tier', 0)
                })
                tracker_stats.append({
                    'announce': tracker['url'],
                    'announceState': 1 if tracker.get('status') == 2 else 0,
                    'downloadCount': -1,
                    'hasAnnounced': tracker.get('num_downloaded', 0) > 0,
                    'hasScraped': False,
                    'host': tracker['url'].split('/')[2] if '/' in tracker['url'] else '',
                    'id': tracker.get('tier', 0),
                    'isBackup': False,
                    'lastAnnounceResult': tracker.get('msg', ''),
                    'lastAnnounceStartTime': 0,
                    'lastAnnounceSucceeded': tracker.get('status') == 2,
                    'lastAnnounceTime': 0,
                    'lastScrapeResult': '',
                    'lastScrapeStartTime': 0,
                    'lastScrapeSucceeded': False,
                    'lastScrapeTime': 0,
                    'leecherCount': tracker.get('num_leeches', -1),
                    'nextAnnounceTime': 0,
                    'nextScrapeTime': 0,
                    'scrape': '',
                    'scrapeState': 0,
                    'seederCount': tracker.get('num_seeds', -1),
                    'tier': tracker.get('tier', 0)
                })

        # Format files - Transmission has multiple related arrays
        files_array = []        # name, length, bytesCompleted
        file_stats = []         # bytesCompleted, wanted, priority
        priorities_array = []   # just priority values
        wanted_array = []       # just wanted values

        for idx, file in enumerate(files):
            # Map qBittorrent priority to Transmission priority
            # qBT: 0=do not download, 1=normal, 6/7=high
            # Transmission: wanted (true/false), priority (-1=low, 0=normal, 1=high)
            qbt_priority = file.get('priority', 1)
            wanted = qbt_priority > 0  # priority 0 means do not download
            if qbt_priority >= 6:
                tr_priority = 1  # high
            elif qbt_priority > 0:
                tr_priority = 0  # normal
            else:
                tr_priority = 0  # unwanted files don't need priority

            bytes_completed = int(file['size'] * file['progress'])

            # files array - basic file info
            files_array.append({
                'bytesCompleted': bytes_completed,
                'length': file['size'],
                'name': file['name']
            })

            # fileStats array - per-file stats
            file_stats.append({
                'bytesCompleted': bytes_completed,
                'wanted': wanted,
                'priority': tr_priority
            })

            # Separate arrays for priorities and wanted
            priorities_array.append(tr_priority)
            wanted_array.append(wanted)

        # Build Transmission torrent object
        transmission_torrent = {
            'activityDate': int(properties.get('last_seen', 0)),
            'addedDate': int(properties.get('addition_date', 0)),
            'bandwidthPriority': 0,
            'comment': properties.get('comment', ''),
            'corruptEver': 0,
            'creator': properties.get('creator', ''),
            'dateCreated': int(properties.get('creation_date', 0)),
            'desiredAvailable': qbt_torrent.get('size', 0) - qbt_torrent.get('completed', 0),
            'doneDate': int(qbt_torrent.get('completion_on', 0)),
            'downloadDir': qbt_torrent.get('save_path', ''),
            'downloadedEver': downloaded,
            'downloadLimit': qbt_torrent.get('dl_limit', -1) // 1024 if qbt_torrent.get('dl_limit', -1) > 0 else qbt_torrent.get('dl_limit', -1),  # Convert bytes/s to KB/s
            'downloadLimited': qbt_torrent.get('dl_limit', -1) > 0,
            'error': 0,
            'errorString': '',
            'eta': qbt_torrent.get('eta', -1) if qbt_torrent.get('eta', 8640000) != 8640000 else -1,
            'files': files_array,
            'fileStats': file_stats,
            'hashString': torrent_hash,
            'haveUnchecked': 0,
            'haveValid': qbt_torrent.get('completed', 0),
            'honorsSessionLimits': True,  # qBittorrent always honors global limits
            'id': sequential_id,  # Sequential ID (1, 2, 3, ...)
            'isFinished': qbt_torrent.get('progress', 0) >= 1.0,
            'isPrivate': properties.get('is_private', False),
            'isStalled': 'stalled' in qbt_torrent.get('state', ''),
            'labels': qbt_torrent.get('tags', '').split(', ') if qbt_torrent.get('tags') else [],
            'leftUntilDone': qbt_torrent.get('size', 0) - qbt_torrent.get('completed', 0),
            'magnetLink': properties.get('magnet_uri', ''),
            'manualAnnounceTime': -1,
            'maxConnectedPeers': 100,
            'metadataPercentComplete': 1.0 if 'meta' not in qbt_torrent.get('state', '') else 0.0,
            'name': qbt_torrent.get('name', ''),
            'peer-limit': 100,
            'peers': [],
            'peersConnected': qbt_torrent.get('num_leechs', 0) + qbt_torrent.get('num_seeds', 0),
            'peersFrom': {
                'fromCache': 0,
                'fromDht': 0,
                'fromIncoming': 0,
                'fromLpd': 0,
                'fromLtep': 0,
                'fromPex': 0,
                'fromTracker': qbt_torrent.get('num_leechs', 0) + qbt_torrent.get('num_seeds', 0)
            },
            'peersGettingFromUs': qbt_torrent.get('num_leechs', 0),
            'peersSendingToUs': qbt_torrent.get('num_seeds', 0),
            'percentDone': qbt_torrent.get('progress', 0),
            'pieces': '',
            'pieceCount': properties.get('nb_pieces', 0),
            'pieceSize': properties.get('piece_size', 0),
            'priorities': priorities_array,
            'queuePosition': qbt_torrent.get('priority', 0),
            'rateDownload': download_rate,
            'rateUpload': upload_rate,
            'recheckProgress': 0,
            'secondsDownloading': properties.get('time_elapsed', 0),
            'secondsSeeding': properties.get('seeding_time', 0),
            'seedIdleLimit': 30,
            'seedIdleMode': 0,
            'seedRatioLimit': 2.0,
            'seedRatioMode': 0,
            'sizeWhenDone': qbt_torrent.get('size', 0),
            'startDate': int(properties.get('addition_date', 0)),
            'status': status,
            'trackers': tracker_list,
            'trackerStats': tracker_stats,
            'totalSize': qbt_torrent.get('size', 0),
            'torrentFile': '',
            'uploadedEver': uploaded,
            'uploadLimit': qbt_torrent.get('up_limit', -1) // 1024 if qbt_torrent.get('up_limit', -1) > 0 else qbt_torrent.get('up_limit', -1),  # Convert bytes/s to KB/s
            'uploadLimited': qbt_torrent.get('up_limit', -1) > 0,
            'uploadRatio': ratio,
            'wanted': wanted_array,
            'webseeds': [],
            'webseedsSendingToUs': 0
        }

        log_debug(f"[ID] Generated torrent: {qbt_torrent.get('name', 'unknown')} -> sequential ID {sequential_id} (hash: {torrent_hash[:8]}..., literal ID {int(torrent_hash[:8], 16)})")
        return transmission_torrent

    @staticmethod
    def get_torrent_ids(arguments: Dict, sorted_torrents: List[Dict]) -> Optional[List[str]]:
        """Extract torrent IDs/hashes from Transmission request and convert to qBittorrent hashes

        Transmission API accepts both:
        1. Literal ID values (generated from hash)
        2. Positional indices (1 = first torrent, 2 = second, etc.)
        """
        ids = arguments.get('ids', [])

        # Check if no IDs were specified (None or empty list/string)
        # Don't use 'not ids' because 0 is falsy but valid!
        if ids is None or ids == [] or ids == '':
            return None

        # Handle special string cases
        if isinstance(ids, str):
            if ids == 'recently-active':
                return None
            ids = [ids]
        # Handle single integer/number - convert to list
        elif isinstance(ids, int) or (not isinstance(ids, list) and not isinstance(ids, str)):
            ids = [ids]

        # Convert Transmission IDs to qBittorrent hashes
        hashes = []
        for id_val in ids:
            # If it's already a hash string (40 chars hexadecimal), use it directly
            if isinstance(id_val, str) and len(id_val) == 40:
                # Normalize to lowercase as qBittorrent uses lowercase hashes
                hashes.append(id_val.lower())
            else:
                # It's a Transmission integer ID
                try:
                    target_id = int(id_val)
                    log_debug(f"[ID] Looking for Transmission ID {target_id}")

                    # First, try to find by literal ID (hash-based)
                    found = False
                    for torrent in sorted_torrents:
                        torrent_hash = torrent['hash'].lower()
                        transmission_id = int(torrent_hash[:8], 16)
                        log_debug(f"[ID] Hash {torrent_hash[:8]}... -> Transmission ID {transmission_id}")
                        if transmission_id == target_id:
                            hashes.append(torrent_hash)
                            log_debug(f"[ID] Match found by literal ID! Using hash: {torrent_hash}")
                            found = True
                            break

                    # If not found by literal ID, try as positional index (1-based)
                    if not found:
                        if 1 <= target_id <= len(sorted_torrents):
                            torrent_hash = sorted_torrents[target_id - 1]['hash'].lower()
                            hashes.append(torrent_hash)
                            log_debug(f"[ID] Match found by position {target_id}! Using hash: {torrent_hash}")
                        else:
                            log_warning(f"Could not find torrent with Transmission ID {target_id} (neither as literal ID nor position)")

                except (ValueError, TypeError) as e:
                    log_error(f"Error converting ID {id_val}: {e}")
                    # Don't add invalid IDs to the list

        # Return the list of found hashes
        # Empty list means IDs were requested but none found (return no torrents)
        # None means no IDs were requested (return all)
        return hashes
