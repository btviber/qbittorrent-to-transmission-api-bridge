"""
qBittorrent WebUI API Client
"""

import requests
from typing import Dict, List, Optional
from logging_utils import log_debug, log_error


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
        response = self.session.post(
            f"{self.url}/api/v2/torrents/start",
            data={"hashes": hash_string}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully started {len(hashes)} torrent(s)")
        else:
            log_error(f"[QBT] Failed to start torrents: {response.status_code} - {response.text}")
        return response.ok

    def stop_torrents(self, hashes: List[str]) -> bool:
        """Stop torrents"""
        self.login()
        hash_string = "|".join(hashes)
        log_debug(f"[QBT] Stopping torrents: {hash_string}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/stop",
            data={"hashes": hash_string}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully stopped {len(hashes)} torrent(s)")
        else:
            log_error(f"[QBT] Failed to stop torrents: {response.status_code} - {response.text}")
        return response.ok

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
        response = self.session.post(
            f"{self.url}/api/v2/torrents/setLocation",
            data={"hashes": hash_string, "location": location}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully set location for {len(hashes)} torrent(s)")
        else:
            log_error(f"[QBT] Failed to set location: {response.status_code} - {response.text}")
        return response.ok

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
        response = self.session.post(
            f"{self.url}/api/v2/torrents/addTrackers",
            data={"hash": torrent_hash, "urls": urls_string}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully added {len(urls)} tracker(s)")
        else:
            log_error(f"[QBT] Failed to add trackers: {response.status_code} - {response.text}")
        return response.ok

    def remove_trackers(self, torrent_hash: str, urls: List[str]) -> bool:
        """Remove trackers from a torrent"""
        self.login()
        urls_string = "|".join(urls)
        log_debug(f"[QBT] Removing trackers from torrent {torrent_hash}: {urls}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/removeTrackers",
            data={"hash": torrent_hash, "urls": urls_string}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully removed {len(urls)} tracker(s)")
        else:
            log_error(f"[QBT] Failed to remove trackers: {response.status_code} - {response.text}")
        return response.ok

    def edit_tracker(self, torrent_hash: str, orig_url: str, new_url: str) -> bool:
        """Edit/replace a tracker URL"""
        self.login()
        log_debug(f"[QBT] Editing tracker for torrent {torrent_hash}: {orig_url} -> {new_url}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/editTracker",
            data={"hash": torrent_hash, "origUrl": orig_url, "newUrl": new_url}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully edited tracker")
        else:
            log_error(f"[QBT] Failed to edit tracker: {response.status_code} - {response.text}")
        return response.ok

    def rename_torrent(self, torrent_hash: str, new_name: str) -> bool:
        """Rename a torrent"""
        self.login()
        log_debug(f"[QBT] Renaming torrent {torrent_hash} to: {new_name}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/rename",
            data={"hash": torrent_hash, "name": new_name}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully renamed torrent")
        else:
            log_error(f"[QBT] Failed to rename torrent: {response.status_code} - {response.text}")
        return response.ok

    def rename_file(self, torrent_hash: str, old_path: str, new_path: str) -> bool:
        """Rename a file within a torrent"""
        self.login()
        log_debug(f"[QBT] Renaming file in torrent {torrent_hash}: {old_path} -> {new_path}")
        response = self.session.post(
            f"{self.url}/api/v2/torrents/renameFile",
            data={"hash": torrent_hash, "oldPath": old_path, "newPath": new_path}
        )
        if response.ok:
            log_debug(f"[QBT] Successfully renamed file")
        else:
            log_error(f"[QBT] Failed to rename file: {response.status_code} - {response.text}")
        return response.ok

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
