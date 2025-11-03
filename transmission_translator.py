"""
Transmission RPC to qBittorrent API Translation
"""

from typing import Dict, List, Optional
from qbittorrent_client import QBittorrentClient
from logging_utils import log_warning, log_error


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
    def qbt_to_transmission_torrent(qbt_torrent: Dict, qbt_client: QBittorrentClient) -> Dict:
        """Convert qBittorrent torrent to Transmission format"""

        torrent_hash = qbt_torrent['hash']
        properties = qbt_client.get_torrent_properties(torrent_hash)
        trackers = qbt_client.get_torrent_trackers(torrent_hash)
        files = qbt_client.get_torrent_files(torrent_hash)

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

        # Format files
        file_stats = []
        for idx, file in enumerate(files):
            file_stats.append({
                'bytesCompleted': int(file['size'] * file['progress']),
                'length': file['size'],
                'name': file['name'],
                'priority': 0,
                'wanted': not file.get('is_seed', True)
            })

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
            'downloadLimit': qbt_torrent.get('dl_limit', -1),
            'downloadLimited': qbt_torrent.get('dl_limit', -1) > 0,
            'error': 0,
            'errorString': '',
            'eta': qbt_torrent.get('eta', -1) if qbt_torrent.get('eta', 8640000) != 8640000 else -1,
            'files': file_stats,
            'fileStats': file_stats,
            'hashString': torrent_hash,
            'haveUnchecked': 0,
            'haveValid': qbt_torrent.get('completed', 0),
            'honorsSessionLimits': True,
            'id': int(torrent_hash[:8], 16),  # Convert first 8 chars of hash to int
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
            'priorities': [],
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
            'uploadLimit': qbt_torrent.get('up_limit', -1),
            'uploadLimited': qbt_torrent.get('up_limit', -1) > 0,
            'uploadRatio': ratio,
            'wanted': [],
            'webseeds': [],
            'webseedsSendingToUs': 0
        }

        return transmission_torrent

    @staticmethod
    def get_torrent_ids(arguments: Dict, qbt_client: QBittorrentClient) -> Optional[List[str]]:
        """Extract torrent IDs/hashes from Transmission request and convert to qBittorrent hashes"""
        ids = arguments.get('ids', [])

        if not ids:
            return None

        if isinstance(ids, str):
            if ids == 'recently-active':
                return None
            ids = [ids]

        # Convert Transmission IDs to qBittorrent hashes
        hashes = []
        for id_val in ids:
            # If it's already a hash string (40 chars hexadecimal), use it directly
            if isinstance(id_val, str) and len(id_val) == 40:
                # Normalize to lowercase as qBittorrent uses lowercase hashes
                hashes.append(id_val.lower())
            else:
                # It's a Transmission integer ID, need to find the corresponding hash
                # Transmission ID is generated from first 8 chars of hash
                try:
                    target_id = int(id_val)
                    # Get all torrents and find the one with matching ID
                    torrents = qbt_client.get_torrents()
                    for torrent in torrents:
                        torrent_hash = torrent['hash'].lower()
                        # Reconstruct the Transmission ID from hash
                        transmission_id = int(torrent_hash[:8], 16)
                        if transmission_id == target_id:
                            hashes.append(torrent_hash)
                            break
                    else:
                        log_warning(f"Could not find torrent with Transmission ID {target_id}")
                except (ValueError, TypeError) as e:
                    log_error(f"Error converting ID {id_val}: {e}")
                    # Try using it as-is as a fallback
                    hashes.append(str(id_val).lower())

        return hashes if hashes else None
