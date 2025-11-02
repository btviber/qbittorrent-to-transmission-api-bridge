#!/usr/bin/env python3
"""
qBittorrent WebUI API to Transmission RPC Translation Layer
"""

from flask import Flask, request, jsonify
import requests
from requests.auth import HTTPBasicAuth
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional

app = Flask(__name__)

# Configuration
QBITTORRENT_URL = "http://localhost:8080"
QBITTORRENT_USERNAME = "admin"
QBITTORRENT_PASSWORD = "password"

# Session management
qbt_session = requests.Session()
qbt_logged_in = False


class QBittorrentClient:
    """Handle qBittorrent WebUI API communication"""
    
    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.logged_in = False
    
    def login(self) -> bool:
        """Login to qBittorrent"""
        if self.logged_in:
            return True

        try:
            print(f"[QBT] Attempting login to {self.url}")
            response = self.session.post(
                f"{self.url}/api/v2/auth/login",
                data={"username": self.username, "password": self.password}
            )
            self.logged_in = response.text == "Ok."
            if self.logged_in:
                print(f"[QBT] Login successful")
            else:
                print(f"[QBT] Login failed: {response.text}")
            return self.logged_in
        except Exception as e:
            print(f"[QBT] Login error: {e}")
            return False
    
    def get_torrents(self, torrent_hash: Optional[str] = None) -> List[Dict]:
        """Get torrent list"""
        self.login()
        url = f"{self.url}/api/v2/torrents/info"
        if torrent_hash:
            url += f"?hashes={torrent_hash}"
        print(f"[QBT] Getting torrents from: {url}")
        response = self.session.get(url)
        if response.ok:
            torrents = response.json()
            print(f"[QBT] Retrieved {len(torrents)} torrent(s)")
            return torrents
        else:
            print(f"[QBT] Failed to get torrents: {response.status_code}")
            return []
    
    def get_torrent_properties(self, torrent_hash: str) -> Dict:
        """Get detailed torrent properties"""
        self.login()
        print(f"[QBT] Getting properties for torrent: {torrent_hash}")
        response = self.session.get(
            f"{self.url}/api/v2/torrents/properties",
            params={"hash": torrent_hash}
        )
        if response.ok:
            print(f"[QBT] Retrieved properties successfully")
            return response.json()
        else:
            print(f"[QBT] Failed to get properties: {response.status_code}")
            return {}
    
    def get_torrent_trackers(self, torrent_hash: str) -> List[Dict]:
        """Get torrent trackers"""
        self.login()
        print(f"[QBT] Getting trackers for torrent: {torrent_hash}")
        response = self.session.get(
            f"{self.url}/api/v2/torrents/trackers",
            params={"hash": torrent_hash}
        )
        if response.ok:
            trackers = response.json()
            print(f"[QBT] Retrieved {len(trackers)} tracker(s)")
            return trackers
        else:
            print(f"[QBT] Failed to get trackers: {response.status_code}")
            return []
    
    def get_torrent_files(self, torrent_hash: str) -> List[Dict]:
        """Get torrent files"""
        self.login()
        print(f"[QBT] Getting files for torrent: {torrent_hash}")
        response = self.session.get(
            f"{self.url}/api/v2/torrents/files",
            params={"hash": torrent_hash}
        )
        if response.ok:
            files = response.json()
            print(f"[QBT] Retrieved {len(files)} file(s)")
            return files
        else:
            print(f"[QBT] Failed to get files: {response.status_code}")
            return []
    
    def add_torrent(self, **kwargs) -> bool:
        """Add a torrent"""
        self.login()

        files = {}
        data = {}

        if 'torrent' in kwargs:
            files['torrents'] = kwargs['torrent']

        if 'filename' in kwargs:
            data['urls'] = kwargs['filename']

        if 'download_dir' in kwargs:
            data['savepath'] = kwargs['download_dir']

        if 'paused' in kwargs:
            data['paused'] = 'true' if kwargs['paused'] else 'false'

        print(f"[QBT] Adding torrent with data: {data}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/add",
            data=data,
            files=files if files else None
        )
        success = response.text == "Ok."
        print(f"[QBT] Add torrent result: {'Success' if success else 'Failed'} - {response.text}")
        return success
    
    def start_torrents(self, hashes: List[str]) -> bool:
        """Start torrents"""
        self.login()
        hash_string = "|".join(hashes)
        print(f"[QBT] Starting torrents: {hash_string}")

        # Try different endpoint variations (ordered by most common first)
        endpoints = [
            "/api/v2/torrents/start",    # Most qBittorrent versions
            "/api/v2/torrents/resume",   # Alternative name
            "/command/resume",            # Older API
            "/command/start"              # Older API alternative
        ]

        data = {"hashes": hash_string}

        for endpoint in endpoints:
            url = f"{self.url}{endpoint}"
            try:
                response = self.session.post(url, data=data)

                if response.ok:
                    print(f"[QBT] Successfully started {len(hashes)} torrent(s)")
                    return True
                elif response.status_code != 404:
                    # Got a response that's not 404, so endpoint exists but request failed
                    print(f"[QBT] Failed to start torrents: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                print(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        print("[QBT] Could not start torrents - no valid API endpoint found")
        return False
    
    def stop_torrents(self, hashes: List[str]) -> bool:
        """Stop torrents"""
        self.login()
        hash_string = "|".join(hashes)
        print(f"[QBT] Stopping torrents: {hash_string}")

        # Try different endpoint variations (ordered by most common first)
        endpoints = [
            "/api/v2/torrents/stop",     # Most qBittorrent versions
            "/api/v2/torrents/pause",    # Alternative name
            "/command/pause",             # Older API
            "/command/stop"               # Older API alternative
        ]

        data = {"hashes": hash_string}

        for endpoint in endpoints:
            url = f"{self.url}{endpoint}"
            try:
                response = self.session.post(url, data=data)

                if response.ok:
                    print(f"[QBT] Successfully stopped {len(hashes)} torrent(s)")
                    return True
                elif response.status_code != 404:
                    # Got a response that's not 404, so endpoint exists but request failed
                    print(f"[QBT] Failed to stop torrents: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                print(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        print("[QBT] Could not stop torrents - no valid API endpoint found")
        return False
    
    def remove_torrents(self, hashes: List[str], delete_data: bool = False) -> bool:
        """Remove torrents"""
        self.login()
        hash_string = "|".join(hashes)
        print(f"[QBT] Removing torrents: {hash_string} (delete_data={delete_data})")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/delete",
            data={
                "hashes": hash_string,
                "deleteFiles": "true" if delete_data else "false"
            }
        )
        if response.ok:
            print(f"[QBT] Successfully removed {len(hashes)} torrent(s)")
        else:
            print(f"[QBT] Failed to remove torrents: {response.status_code} - {response.text}")
        return response.ok
    
    def verify_torrents(self, hashes: List[str]) -> bool:
        """Verify torrents"""
        self.login()
        hash_string = "|".join(hashes)
        print(f"[QBT] Verifying torrents: {hash_string}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/recheck",
            data={"hashes": hash_string}
        )
        if response.ok:
            print(f"[QBT] Successfully started verification for {len(hashes)} torrent(s)")
        else:
            print(f"[QBT] Failed to verify torrents: {response.status_code} - {response.text}")
        return response.ok
    
    def set_torrent_location(self, hashes: List[str], location: str) -> bool:
        """Set torrent location (always moves files in qBittorrent)"""
        self.login()
        hash_string = "|".join(hashes)
        print(f"[QBT] Setting location for torrents: {hash_string} to: {location}")

        # Try different endpoint variations
        endpoints = [
            "/api/v2/torrents/setLocation",
            "/command/setLocation"
        ]

        data = {"hashes": hash_string, "location": location}

        for endpoint in endpoints:
            url = f"{self.url}{endpoint}"
            try:
                response = self.session.post(url, data=data)

                if response.ok:
                    print(f"[QBT] Successfully set location for {len(hashes)} torrent(s)")
                    return True
                elif response.status_code != 404:
                    # Got a response that's not 404, so endpoint exists but request failed
                    print(f"[QBT] Failed to set location: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                print(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        print("[QBT] Could not set torrent location - no valid API endpoint found")
        return False
    
    def reannounce_torrents(self, hashes: List[str]) -> bool:
        """Reannounce to trackers"""
        self.login()
        hash_string = "|".join(hashes)
        print(f"[QBT] Reannouncing torrents: {hash_string}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/reannounce",
            data={"hashes": hash_string}
        )
        if response.ok:
            print(f"[QBT] Successfully reannounced {len(hashes)} torrent(s)")
        else:
            print(f"[QBT] Failed to reannounce torrents: {response.status_code} - {response.text}")
        return response.ok

    def add_trackers(self, torrent_hash: str, urls: List[str]) -> bool:
        """Add trackers to a torrent"""
        self.login()
        urls_string = "\n".join(urls)
        print(f"[QBT] Adding trackers to torrent {torrent_hash}: {urls}")

        # Try different endpoint variations
        endpoints = [
            "/api/v2/torrents/addTrackers",
            "/command/addTrackers"
        ]

        data = {"hash": torrent_hash, "urls": urls_string}

        for endpoint in endpoints:
            url = f"{self.url}{endpoint}"
            try:
                response = self.session.post(url, data=data)

                if response.ok:
                    print(f"[QBT] Successfully added {len(urls)} tracker(s)")
                    return True
                elif response.status_code != 404:
                    print(f"[QBT] Failed to add trackers: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                print(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        print("[QBT] Could not add trackers - no valid API endpoint found")
        return False

    def remove_trackers(self, torrent_hash: str, urls: List[str]) -> bool:
        """Remove trackers from a torrent"""
        self.login()
        urls_string = "|".join(urls)
        print(f"[QBT] Removing trackers from torrent {torrent_hash}: {urls}")

        # Try different endpoint variations
        endpoints = [
            "/api/v2/torrents/removeTrackers",
            "/command/removeTrackers"
        ]

        data = {"hash": torrent_hash, "urls": urls_string}

        for endpoint in endpoints:
            url = f"{self.url}{endpoint}"
            try:
                response = self.session.post(url, data=data)

                if response.ok:
                    print(f"[QBT] Successfully removed {len(urls)} tracker(s)")
                    return True
                elif response.status_code != 404:
                    print(f"[QBT] Failed to remove trackers: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                print(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        print("[QBT] Could not remove trackers - no valid API endpoint found")
        return False

    def edit_tracker(self, torrent_hash: str, orig_url: str, new_url: str) -> bool:
        """Edit/replace a tracker URL"""
        self.login()
        print(f"[QBT] Editing tracker for torrent {torrent_hash}: {orig_url} -> {new_url}")

        # Try different endpoint variations
        endpoints = [
            "/api/v2/torrents/editTracker",
            "/command/editTracker"
        ]

        data = {"hash": torrent_hash, "origUrl": orig_url, "newUrl": new_url}

        for endpoint in endpoints:
            url = f"{self.url}{endpoint}"
            try:
                response = self.session.post(url, data=data)

                if response.ok:
                    print(f"[QBT] Successfully edited tracker")
                    return True
                elif response.status_code != 404:
                    print(f"[QBT] Failed to edit tracker: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                print(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        print("[QBT] Could not edit tracker - no valid API endpoint found")
        return False


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
                        print(f"Warning: Could not find torrent with Transmission ID {target_id}")
                except (ValueError, TypeError) as e:
                    print(f"Error converting ID {id_val}: {e}")
                    # Try using it as-is as a fallback
                    hashes.append(str(id_val).lower())

        return hashes if hashes else None


# Initialize qBittorrent client
qbt_client = QBittorrentClient(QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD)


@app.route('/transmission/rpc', methods=['POST'])
def transmission_rpc():
    """Main Transmission RPC endpoint"""

    try:
        data = request.get_json()
        method = data.get('method', '')
        arguments = data.get('arguments', {})
        tag = data.get('tag')

        print(f"\n[RPC] ===== Incoming Request =====")
        print(f"[RPC] Method: {method}")
        print(f"[RPC] Tag: {tag}")
        print(f"[RPC] Arguments: {arguments}")

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

        elif method == 'session-get':
            result = handle_session_get(arguments)

        elif method == 'session-stats':
            result = handle_session_stats(arguments)

        else:
            print(f"[RPC] ERROR: Unknown method '{method}'")
            return jsonify({
                'result': 'error',
                'tag': tag
            })

        print(f"[RPC] Response: success")
        return jsonify({
            'arguments': result,
            'result': 'success',
            'tag': tag
        })

    except Exception as e:
        print(f"[RPC] ERROR: Exception during request handling: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'result': str(e),
            'tag': data.get('tag') if 'data' in locals() else None
        }), 500


def handle_torrent_get(arguments: Dict) -> Dict:
    """Handle torrent-get method"""
    print(f"[RPC] torrent-get")
    fields = arguments.get('fields', [])
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)

    print(f"[RPC] Requested fields: {fields if fields else 'all'}")
    print(f"[RPC] Requested IDs: {ids if ids else 'all'}")

    torrents = []
    qbt_torrents = qbt_client.get_torrents()

    for qbt_torrent in qbt_torrents:
        if ids is None or qbt_torrent['hash'] in ids:
            transmission_torrent = TransmissionTranslator.qbt_to_transmission_torrent(
                qbt_torrent, qbt_client
            )

            # Filter fields if specified
            if fields:
                transmission_torrent = {
                    k: v for k, v in transmission_torrent.items()
                    if k in fields
                }

            torrents.append(transmission_torrent)

    print(f"[RPC] Returning {len(torrents)} torrent(s)")
    return {'torrents': torrents}


def handle_torrent_add(arguments: Dict) -> Dict:
    """Handle torrent-add method"""
    print(f"[RPC] torrent-add")
    kwargs = {}

    if 'filename' in arguments:
        kwargs['filename'] = arguments['filename']
        print(f"[RPC] Adding from URL: {arguments['filename']}")

    if 'metainfo' in arguments:
        import base64
        kwargs['torrent'] = base64.b64decode(arguments['metainfo'])
        print(f"[RPC] Adding from metainfo (base64 decoded)")

    if 'download-dir' in arguments:
        kwargs['download_dir'] = arguments['download-dir']
        print(f"[RPC] Download directory: {arguments['download-dir']}")

    if 'paused' in arguments:
        kwargs['paused'] = arguments['paused']
        print(f"[RPC] Paused: {arguments['paused']}")

    success = qbt_client.add_torrent(**kwargs)

    if success:
        print(f"[RPC] Torrent added successfully")
        # Get the newly added torrent
        torrents = qbt_client.get_torrents()
        if torrents:
            newest_torrent = max(torrents, key=lambda x: x.get('added_on', 0))
            transmission_torrent = TransmissionTranslator.qbt_to_transmission_torrent(
                newest_torrent, qbt_client
            )
            return {'torrent-added': transmission_torrent}
    else:
        print(f"[RPC] Failed to add torrent")

    return {}


def handle_torrent_start(arguments: Dict) -> Dict:
    """Handle torrent-start method"""
    print(f"[RPC] torrent-start")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    if ids:
        qbt_client.start_torrents(ids)
    else:
        print("[RPC] Warning: No valid torrent IDs provided for start")
    return {}


def handle_torrent_stop(arguments: Dict) -> Dict:
    """Handle torrent-stop method"""
    print(f"[RPC] torrent-stop")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    if ids:
        qbt_client.stop_torrents(ids)
    else:
        print("[RPC] Warning: No valid torrent IDs provided for stop")
    return {}


def handle_torrent_verify(arguments: Dict) -> Dict:
    """Handle torrent-verify method"""
    print(f"[RPC] torrent-verify")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    if ids:
        qbt_client.verify_torrents(ids)
    else:
        print("[RPC] Warning: No valid torrent IDs provided for verify")
    return {}


def handle_torrent_reannounce(arguments: Dict) -> Dict:
    """Handle torrent-reannounce method"""
    print(f"[RPC] torrent-reannounce")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    if ids:
        qbt_client.reannounce_torrents(ids)
    else:
        print("[RPC] Warning: No valid torrent IDs provided for reannounce")
    return {}


def handle_torrent_set(arguments: Dict) -> Dict:
    """Handle torrent-set method"""
    print(f"[RPC] torrent-set: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)

    if not ids:
        print("[RPC] Warning: No valid torrent IDs provided for torrent-set")
        return {}

    # Handle tracker operations
    if 'trackerAdd' in arguments:
        trackers = arguments['trackerAdd']
        print(f"[RPC] trackerAdd detected: {trackers}")
        for torrent_hash in ids:
            qbt_client.add_trackers(torrent_hash, trackers)

    if 'trackerRemove' in arguments:
        tracker_ids = arguments['trackerRemove']
        print(f"[RPC] trackerRemove detected: {tracker_ids}")
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
                            print(f"[RPC] Will remove tracker ID {tracker_id}: {tracker['url']}")
                        break

            if urls_to_remove:
                qbt_client.remove_trackers(torrent_hash, urls_to_remove)

    if 'trackerReplace' in arguments:
        tracker_replace = arguments['trackerReplace']
        print(f"[RPC] trackerReplace detected: {tracker_replace}")

        if not tracker_replace or len(tracker_replace) < 2:
            print("[RPC] Warning: Invalid trackerReplace format, expected [tracker_id, new_url]")
            return {}

        tracker_id = tracker_replace[0]
        new_url = tracker_replace[1]
        print(f"[RPC] Replacing tracker ID {tracker_id} with: {new_url}")

        # Replace tracker for each torrent
        for torrent_hash in ids:
            trackers = qbt_client.get_torrent_trackers(torrent_hash)

            # Find the tracker by ID (tier)
            for tracker in trackers:
                if tracker.get('tier') == tracker_id and tracker.get('url'):
                    old_url = tracker['url']
                    if old_url not in ['** [DHT] **', '** [PeX] **', '** [LSD] **']:
                        print(f"[RPC] Found tracker to replace: {old_url}")
                        qbt_client.edit_tracker(torrent_hash, old_url, new_url)
                    break

    # Handle other torrent-set operations
    # TODO: Implement other settings like speed limits, peer limits, etc.

    return {}


def handle_torrent_remove(arguments: Dict) -> Dict:
    """Handle torrent-remove method"""
    print(f"[RPC] torrent-remove")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    delete_data = arguments.get('delete-local-data', False)
    print(f"[RPC] Delete local data: {delete_data}")

    if ids:
        qbt_client.remove_torrents(ids, delete_data)
    else:
        print("[RPC] Warning: No valid torrent IDs provided for remove")
    return {}


def handle_torrent_set_location(arguments: Dict) -> Dict:
    """Handle torrent-set-location method"""
    print(f"[RPC] torrent-set-location: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    location = arguments.get('location', '')
    move = arguments.get('move', True)  # Transmission default is True

    if not ids:
        print("[RPC] Warning: No torrent IDs provided for set-location")
        return {}

    if not location:
        print("[RPC] Warning: No location provided for set-location")
        return {}

    # Note: qBittorrent's setLocation always moves files
    # If move=False in Transmission, this is a mismatch in behavior
    if not move:
        print("[RPC] Warning: qBittorrent always moves files. 'move=false' not supported")

    qbt_client.set_torrent_location(ids, location)
    return {}


def handle_tracker_add(arguments: Dict) -> Dict:
    """Handle torrent-tracker-add method (Transmission: trackerAdd)"""
    print(f"[RPC] tracker-add: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    trackers = arguments.get('trackerAdd', [])

    if not ids:
        print("[RPC] Warning: No torrent IDs provided for tracker-add")
        return {}

    if not trackers:
        print("[RPC] Warning: No trackers provided for tracker-add")
        return {}

    # Add trackers to each torrent
    for torrent_hash in ids:
        qbt_client.add_trackers(torrent_hash, trackers)

    return {}


def handle_tracker_remove(arguments: Dict) -> Dict:
    """Handle torrent-tracker-remove method (Transmission: trackerRemove)"""
    print(f"[RPC] tracker-remove: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    tracker_ids = arguments.get('trackerRemove', [])

    if not ids:
        print("[RPC] Warning: No torrent IDs provided for tracker-remove")
        return {}

    if not tracker_ids:
        print("[RPC] Warning: No tracker IDs provided for tracker-remove")
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
    print(f"[RPC] tracker-replace: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    tracker_replace = arguments.get('trackerReplace', [])

    if not ids:
        print("[RPC] Warning: No torrent IDs provided for tracker-replace")
        return {}

    if not tracker_replace or len(tracker_replace) < 2:
        print("[RPC] Warning: Invalid trackerReplace format, expected [tracker_id, new_url]")
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
        'version': '3.00 (qBittorrent bridge)'
    }


def handle_session_stats(arguments: Dict) -> Dict:
    """Handle session-stats method"""
    return {
        'activeTorrentCount': 0,
        'downloadSpeed': 0,
        'pausedTorrentCount': 0,
        'torrentCount': 0,
        'uploadSpeed': 0,
        'cumulative-stats': {
            'downloadedBytes': 0,
            'filesAdded': 0,
            'secondsActive': 0,
            'sessionCount': 1,
            'uploadedBytes': 0
        },
        'current-stats': {
            'downloadedBytes': 0,
            'filesAdded': 0,
            'secondsActive': 0,
            'sessionCount': 1,
            'uploadedBytes': 0
        }
    }


if __name__ == '__main__':
    print("Starting qBittorrent to Transmission RPC translation layer...")
    print(f"Connecting to qBittorrent at: {QBITTORRENT_URL}")
    print("Listening on http://localhost:9091/transmission/rpc")
    app.run(host='0.0.0.0', port=9091, debug=True)
