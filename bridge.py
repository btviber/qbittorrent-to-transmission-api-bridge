#!/usr/bin/env python3
"""
qBittorrent WebUI API to Transmission RPC Translation Layer
"""

from flask import Flask, request, jsonify
import requests
from requests.auth import HTTPBasicAuth
import json
import hashlib
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

app = Flask(__name__)

# Configuration
QBITTORRENT_URL = "http://localhost:8080"
QBITTORRENT_USERNAME = "admin"
QBITTORRENT_PASSWORD = "password"

# Verbosity levels:
# 0 = Errors and warnings only
# 1 = RPC operations (client actions) (-v)
# 2 = Full debug (including qBittorrent API calls) (-vv)
VERBOSITY = 0

def log_error(message: str):
    """Always print errors"""
    print(f"[ERROR] {message}")

def log_warning(message: str):
    """Always print warnings"""
    print(f"[WARNING] {message}")

def log_info(message: str):
    """Print info messages at verbosity level 1+ (RPC operations)"""
    if VERBOSITY >= 1:
        print(message)

def log_debug(message: str):
    """Print debug messages at verbosity level 2+ (QBT API calls)"""
    if VERBOSITY >= 2:
        print(message)

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
            log_debug(f"[QBT] Attempting login to {self.url}")
            response = self.session.post(
                f"{self.url}/api/v2/auth/login",
                data={"username": self.username, "password": self.password}
            )
            self.logged_in = response.text == "Ok."
            if self.logged_in:
                log_debug(f"[QBT] Login successful")
            else:
                log_error(f"[QBT] Login failed: {response.text}")
            return self.logged_in
        except Exception as e:
            log_error(f"[QBT] Login error: {e}")
            return False
    
    def get_torrents(self, torrent_hash: Optional[str] = None) -> List[Dict]:
        """Get torrent list"""
        self.login()
        url = f"{self.url}/api/v2/torrents/info"
        if torrent_hash:
            url += f"?hashes={torrent_hash}"
        log_debug(f"[QBT] Getting torrents from: {url}")
        response = self.session.get(url)
        if response.ok:
            torrents = response.json()
            log_debug(f"[QBT] Retrieved {len(torrents)} torrent(s)")
            return torrents
        else:
            log_error(f"[QBT] Failed to get torrents: {response.status_code}")
            return []
    
    def get_torrent_properties(self, torrent_hash: str) -> Dict:
        """Get detailed torrent properties"""
        self.login()
        log_debug(f"[QBT] Getting properties for torrent: {torrent_hash}")
        response = self.session.get(
            f"{self.url}/api/v2/torrents/properties",
            params={"hash": torrent_hash}
        )
        if response.ok:
            log_debug(f"[QBT] Retrieved properties successfully")
            return response.json()
        else:
            log_error(f"[QBT] Failed to get properties: {response.status_code}")
            return {}
    
    def get_torrent_trackers(self, torrent_hash: str) -> List[Dict]:
        """Get torrent trackers"""
        self.login()
        log_debug(f"[QBT] Getting trackers for torrent: {torrent_hash}")
        response = self.session.get(
            f"{self.url}/api/v2/torrents/trackers",
            params={"hash": torrent_hash}
        )
        if response.ok:
            trackers = response.json()
            log_debug(f"[QBT] Retrieved {len(trackers)} tracker(s)")
            return trackers
        else:
            log_error(f"[QBT] Failed to get trackers: {response.status_code}")
            return []
    
    def get_torrent_files(self, torrent_hash: str) -> List[Dict]:
        """Get torrent files"""
        self.login()
        log_debug(f"[QBT] Getting files for torrent: {torrent_hash}")
        response = self.session.get(
            f"{self.url}/api/v2/torrents/files",
            params={"hash": torrent_hash}
        )
        if response.ok:
            files = response.json()
            log_debug(f"[QBT] Retrieved {len(files)} file(s)")
            return files
        else:
            log_error(f"[QBT] Failed to get files: {response.status_code}")
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
            # qBittorrent WebUI uses 'stopped' parameter (same logic as paused)
            paused_value = kwargs['paused']
            log_debug(f"[QBT] Paused parameter received: {paused_value} (type: {type(paused_value).__name__})")
            # stopped should match paused (True = stopped, False = running)
            data['stopped'] = 'true' if paused_value else 'false'
            log_debug(f"[QBT] Setting stopped={data['stopped']}")

        log_debug(f"[QBT] Adding torrent with data: {data}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/add",
            data=data,
            files=files if files else None
        )
        success = response.text == "Ok."
        if success:
            log_debug(f"[QBT] Add torrent result: Success")
        else:
            log_error(f"[QBT] Add torrent result: Failed - {response.text}")
        return success
    
    def start_torrents(self, hashes: List[str]) -> bool:
        """Start torrents"""
        self.login()
        hash_string = "|".join(hashes)
        log_debug(f"[QBT] Starting torrents: {hash_string}")

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
                    log_debug(f"[QBT] Successfully started {len(hashes)} torrent(s)")
                    return True
                elif response.status_code != 404:
                    # Got a response that's not 404, so endpoint exists but request failed
                    log_error(f"[QBT] Failed to start torrents: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                log_debug(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        log_error("[QBT] Could not start torrents - no valid API endpoint found")
        return False
    
    def stop_torrents(self, hashes: List[str]) -> bool:
        """Stop torrents"""
        self.login()
        hash_string = "|".join(hashes)
        log_debug(f"[QBT] Stopping torrents: {hash_string}")

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
                    log_debug(f"[QBT] Successfully stopped {len(hashes)} torrent(s)")
                    return True
                elif response.status_code != 404:
                    # Got a response that's not 404, so endpoint exists but request failed
                    log_error(f"[QBT] Failed to stop torrents: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                log_debug(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        log_error("[QBT] Could not stop torrents - no valid API endpoint found")
        return False
    
    def remove_torrents(self, hashes: List[str], delete_data: bool = False) -> bool:
        """Remove torrents"""
        self.login()
        hash_string = "|".join(hashes)
        log_debug(f"[QBT] Removing torrents: {hash_string} (delete_data={delete_data})")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/delete",
            data={
                "hashes": hash_string,
                "deleteFiles": "true" if delete_data else "false"
            }
        )
        if response.ok:
            log_debug(f"[QBT] Successfully removed {len(hashes)} torrent(s)")
        else:
            log_error(f"[QBT] Failed to remove torrents: {response.status_code} - {response.text}")
        return response.ok
    
    def verify_torrents(self, hashes: List[str]) -> bool:
        """Verify torrents"""
        self.login()
        hash_string = "|".join(hashes)
        log_debug(f"[QBT] Verifying torrents: {hash_string}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/recheck",
            data={"hashes": hash_string}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully started verification for {len(hashes)} torrent(s)")
        else:
            log_error(f"[QBT] Failed to verify torrents: {response.status_code} - {response.text}")
        return response.ok
    
    def set_torrent_location(self, hashes: List[str], location: str) -> bool:
        """Set torrent location (always moves files in qBittorrent)"""
        self.login()
        hash_string = "|".join(hashes)
        log_debug(f"[QBT] Setting location for torrents: {hash_string} to: {location}")

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
                    log_debug(f"[QBT] Successfully set location for {len(hashes)} torrent(s)")
                    return True
                elif response.status_code != 404:
                    # Got a response that's not 404, so endpoint exists but request failed
                    log_error(f"[QBT] Failed to set location: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                log_debug(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        log_error("[QBT] Could not set torrent location - no valid API endpoint found")
        return False
    
    def reannounce_torrents(self, hashes: List[str]) -> bool:
        """Reannounce to trackers"""
        self.login()
        hash_string = "|".join(hashes)
        log_debug(f"[QBT] Reannouncing torrents: {hash_string}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/reannounce",
            data={"hashes": hash_string}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully reannounced {len(hashes)} torrent(s)")
        else:
            log_error(f"[QBT] Failed to reannounce torrents: {response.status_code} - {response.text}")
        return response.ok

    def add_trackers(self, torrent_hash: str, urls: List[str]) -> bool:
        """Add trackers to a torrent"""
        self.login()
        urls_string = "\n".join(urls)
        log_debug(f"[QBT] Adding trackers to torrent {torrent_hash}: {urls}")

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
                    log_debug(f"[QBT] Successfully added {len(urls)} tracker(s)")
                    return True
                elif response.status_code != 404:
                    log_error(f"[QBT] Failed to add trackers: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                log_debug(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        log_error("[QBT] Could not add trackers - no valid API endpoint found")
        return False

    def remove_trackers(self, torrent_hash: str, urls: List[str]) -> bool:
        """Remove trackers from a torrent"""
        self.login()
        urls_string = "|".join(urls)
        log_debug(f"[QBT] Removing trackers from torrent {torrent_hash}: {urls}")

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
                    log_debug(f"[QBT] Successfully removed {len(urls)} tracker(s)")
                    return True
                elif response.status_code != 404:
                    log_error(f"[QBT] Failed to remove trackers: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                log_debug(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        log_error("[QBT] Could not remove trackers - no valid API endpoint found")
        return False

    def edit_tracker(self, torrent_hash: str, orig_url: str, new_url: str) -> bool:
        """Edit/replace a tracker URL"""
        self.login()
        log_debug(f"[QBT] Editing tracker for torrent {torrent_hash}: {orig_url} -> {new_url}")

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
                    log_debug(f"[QBT] Successfully edited tracker")
                    return True
                elif response.status_code != 404:
                    log_error(f"[QBT] Failed to edit tracker: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                log_debug(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        log_error("[QBT] Could not edit tracker - no valid API endpoint found")
        return False

    def rename_torrent(self, torrent_hash: str, new_name: str) -> bool:
        """Rename a torrent"""
        self.login()
        log_debug(f"[QBT] Renaming torrent {torrent_hash} to: {new_name}")

        # Try different endpoint variations
        endpoints = [
            "/api/v2/torrents/rename",
            "/command/rename"
        ]

        data = {"hash": torrent_hash, "name": new_name}

        for endpoint in endpoints:
            url = f"{self.url}{endpoint}"
            try:
                response = self.session.post(url, data=data)

                if response.ok:
                    log_debug(f"[QBT] Successfully renamed torrent")
                    return True
                elif response.status_code != 404:
                    log_error(f"[QBT] Failed to rename torrent: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                log_debug(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        log_error("[QBT] Could not rename torrent - no valid API endpoint found")
        return False

    def rename_file(self, torrent_hash: str, old_path: str, new_path: str) -> bool:
        """Rename a file within a torrent"""
        self.login()
        log_debug(f"[QBT] Renaming file in torrent {torrent_hash}: {old_path} -> {new_path}")

        # Try different endpoint variations
        endpoints = [
            "/api/v2/torrents/renameFile",
            "/command/renameFile"
        ]

        data = {"hash": torrent_hash, "oldPath": old_path, "newPath": new_path}

        for endpoint in endpoints:
            url = f"{self.url}{endpoint}"
            try:
                response = self.session.post(url, data=data)

                if response.ok:
                    log_debug(f"[QBT] Successfully renamed file")
                    return True
                elif response.status_code != 404:
                    log_error(f"[QBT] Failed to rename file: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                log_debug(f"[QBT] Error with endpoint {endpoint}: {e}")
                continue

        log_error("[QBT] Could not rename file - no valid API endpoint found")
        return False

    def get_transfer_info(self) -> Dict:
        """Get transfer and server statistics"""
        self.login()
        log_debug(f"[QBT] Getting server state from sync/maindata")
        response = self.session.get(f"{self.url}/api/v2/sync/maindata?rid=0")
        if response.ok:
            data = response.json()
            server_state = data.get('server_state', {})
            log_debug(f"[QBT] Retrieved server state: {server_state}")
            return server_state
        else:
            log_error(f"[QBT] Failed to get server state: {response.status_code}")
            return {}


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


def handle_torrent_get(arguments: Dict) -> Dict:
    """Handle torrent-get method"""
    log_info(f"[RPC] torrent-get")
    fields = arguments.get('fields', [])
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)

    log_debug(f"[RPC] Requested fields: {fields if fields else 'all'}")
    log_debug(f"[RPC] Requested IDs: {ids if ids else 'all'}")

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
        import base64
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
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    if ids:
        qbt_client.start_torrents(ids)
    else:
        log_warning("No valid torrent IDs provided for start")
    return {}


def handle_torrent_stop(arguments: Dict) -> Dict:
    """Handle torrent-stop method"""
    log_info(f"[RPC] torrent-stop")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    if ids:
        qbt_client.stop_torrents(ids)
    else:
        log_warning("No valid torrent IDs provided for stop")
    return {}


def handle_torrent_verify(arguments: Dict) -> Dict:
    """Handle torrent-verify method"""
    log_info(f"[RPC] torrent-verify")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    if ids:
        qbt_client.verify_torrents(ids)
    else:
        log_warning("No valid torrent IDs provided for verify")
    return {}


def handle_torrent_reannounce(arguments: Dict) -> Dict:
    """Handle torrent-reannounce method"""
    log_info(f"[RPC] torrent-reannounce")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
    if ids:
        qbt_client.reannounce_torrents(ids)
    else:
        log_warning("No valid torrent IDs provided for reannounce")
    return {}


def handle_torrent_set(arguments: Dict) -> Dict:
    """Handle torrent-set method"""
    log_info(f"[RPC] torrent-set")
    log_debug(f"[RPC] Arguments: {arguments}")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)

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

    # Handle other torrent-set operations
    # TODO: Implement other settings like speed limits, peer limits, etc.

    return {}


def handle_torrent_remove(arguments: Dict) -> Dict:
    """Handle torrent-remove method"""
    log_info(f"[RPC] torrent-remove")
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
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
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
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
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
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
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
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
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
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
    ids = TransmissionTranslator.get_torrent_ids(arguments, qbt_client)
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
        'version': '3.00 (qBittorrent bridge)'
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


def main():
    global VERBOSITY

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
    VERBOSITY = min(args.verbose, 2)  # Cap at level 2

    print("Starting qBittorrent to Transmission RPC Bridge")
    print(f"Verbosity level: {VERBOSITY} {'(errors/warnings only)' if VERBOSITY == 0 else '(info)' if VERBOSITY == 1 else '(full debug)'}")
    print(f"Connecting to qBittorrent at: {QBITTORRENT_URL}")
    print(f"Listening on http://{args.host}:{args.port}/transmission/rpc")
    print()

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == '__main__':
    main()
