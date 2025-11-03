"""
Sync Manager - Background sync with qBittorrent using /api/v2/sync/maindata
Maintains in-memory cache of all torrent data for efficient access
"""

import threading
import time
from typing import Dict, List, Optional
from logging_utils import log_info, log_debug, log_error, log_warning, log_trace
from qbittorrent_client import QBittorrentClient


class SyncManager:
    """Manages background sync with qBittorrent and maintains cache"""

    def __init__(self, qbt_client: QBittorrentClient, poll_interval: float = 1.5):
        """
        Initialize sync manager

        Args:
            qbt_client: QBittorrentClient instance
            poll_interval: How often to poll for updates (seconds)
        """
        self.qbt_client = qbt_client
        self.poll_interval = poll_interval

        # Cache structure
        self._cache = {
            'rid': 0,
            'torrents': {},  # hash -> torrent data
            'server_state': {},
            'categories': {},
            'tags': [],
            'trackers': {}
        }

        # Secondary cache for expensive data (files, trackers, properties)
        # Format: {hash: {
        #   'files': [...], 'has_files': bool,
        #   'trackers': [...], 'has_trackers': bool,
        #   'properties': {...}, 'has_properties': bool,
        #   'timestamp': float
        # }}
        self._detail_cache = {}
        self._detail_cache_ttl = 30  # Cache for 30 seconds

        # Thread safety
        self._lock = threading.RLock()
        self._running = False
        self._thread = None
        self._initialized = threading.Event()

    def start(self):
        """Start the background sync thread"""
        if self._running:
            log_warning("[SYNC] Sync manager already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True, name="SyncThread")
        self._thread.start()
        log_info("[SYNC] Sync manager started")

        # Wait for initial sync to complete
        log_info("[SYNC] Waiting for initial sync...")
        if self._initialized.wait(timeout=10):
            log_info("[SYNC] Initial sync completed")
        else:
            log_error("[SYNC] Initial sync timed out!")

    def stop(self):
        """Stop the background sync thread"""
        if not self._running:
            return

        log_info("[SYNC] Stopping sync manager...")
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        log_info("[SYNC] Sync manager stopped")

    def _sync_loop(self):
        """Background thread main loop"""
        log_info("[SYNC] Sync loop started")

        # Initial full sync
        try:
            self._do_sync(full=True)
            self._initialized.set()
        except Exception as e:
            log_error(f"[SYNC] Initial sync failed: {e}")
            self._initialized.set()  # Release waiters even on failure
            return

        # Continuous incremental sync
        while self._running:
            try:
                time.sleep(self.poll_interval)
                self._do_sync(full=False)
            except Exception as e:
                log_error(f"[SYNC] Sync error: {e}")
                # On error, wait a bit longer before retrying
                time.sleep(5)

    def _do_sync(self, full: bool = False):
        """Perform a sync operation"""
        rid = 0 if full else self._cache['rid']

        log_trace(f"[SYNC] Polling sync/maindata with rid={rid}")
        data = self.qbt_client.get_sync_maindata(rid=rid)

        if not data:
            log_warning("[SYNC] Empty sync response")
            return

        with self._lock:
            # Update rid
            new_rid = data.get('rid', rid)
            self._cache['rid'] = new_rid

            is_full = data.get('full_update', False)

            if is_full:
                # Full update - replace everything
                log_info(f"[SYNC] Full update received, {len(data.get('torrents', {}))} torrents")
                self._cache['torrents'] = data.get('torrents', {})
                self._cache['server_state'] = data.get('server_state', {})
                self._cache['categories'] = data.get('categories', {})
                self._cache['tags'] = data.get('tags', [])
                self._cache['trackers'] = data.get('trackers', {})
            else:
                # Incremental update - merge changes
                torrents_updated = data.get('torrents', {})
                if torrents_updated:
                    log_trace(f"[SYNC] Incremental update: {len(torrents_updated)} torrent(s) changed")
                    for torrent_hash, partial_data in torrents_updated.items():
                        if torrent_hash in self._cache['torrents']:
                            # Merge partial update into existing torrent
                            torrent_name = self._cache['torrents'][torrent_hash].get('name', torrent_hash[:8])
                            changed_fields = list(partial_data.keys())
                            log_trace(f"[SYNC]   {torrent_name}: changed fields = {changed_fields}")
                            self._cache['torrents'][torrent_hash].update(partial_data)
                        else:
                            # New torrent
                            self._cache['torrents'][torrent_hash] = partial_data
                            log_trace(f"[SYNC]   New torrent added: {partial_data.get('name', torrent_hash[:8])}")

                # Handle removed torrents
                torrents_removed = data.get('torrents_removed', [])
                if torrents_removed:
                    log_debug(f"[SYNC] Removing {len(torrents_removed)} torrent(s)")
                    for torrent_hash in torrents_removed:
                        self._cache['torrents'].pop(torrent_hash, None)

                # Update server state if present
                if 'server_state' in data:
                    self._cache['server_state'].update(data['server_state'])

                # Update categories/tags if present
                if 'categories' in data:
                    self._cache['categories'].update(data.get('categories', {}))
                if 'tags' in data:
                    self._cache['tags'] = data.get('tags', [])
                if 'trackers' in data:
                    self._cache['trackers'].update(data.get('trackers', {}))

    def get_torrents(self) -> List[Dict]:
        """Get all torrents from cache (returns list like old API)"""
        with self._lock:
            # Convert dict to list and add 'hash' field for compatibility
            # Sync API uses hash as key, but old API included it in the torrent data
            torrents = []
            for torrent_hash, torrent_data in self._cache['torrents'].items():
                torrent = torrent_data.copy()
                torrent['hash'] = torrent_hash
                torrents.append(torrent)
            return torrents

    def get_torrent_by_hash(self, torrent_hash: str) -> Optional[Dict]:
        """Get a specific torrent by hash"""
        with self._lock:
            torrent_data = self._cache['torrents'].get(torrent_hash.lower())
            if torrent_data:
                torrent = torrent_data.copy()
                torrent['hash'] = torrent_hash.lower()
                return torrent
            return None

    def get_server_state(self) -> Dict:
        """Get server state from cache"""
        with self._lock:
            return self._cache['server_state'].copy()

    def is_ready(self) -> bool:
        """Check if cache is initialized and ready"""
        return self._initialized.is_set()

    def get_cache_stats(self) -> Dict:
        """Get cache statistics for debugging"""
        with self._lock:
            return {
                'rid': self._cache['rid'],
                'torrent_count': len(self._cache['torrents']),
                'categories': len(self._cache['categories']),
                'tags': len(self._cache['tags']),
                'detail_cache_size': len(self._detail_cache),
                'running': self._running,
                'initialized': self._initialized.is_set()
            }

    def get_torrent_details(self, torrent_hash: str, need_files: bool = False,
                           need_trackers: bool = False, need_properties: bool = False) -> Dict:
        """Get cached torrent details (files, trackers, properties) or fetch if needed

        Args:
            torrent_hash: Torrent hash
            need_files: Whether files list is needed
            need_trackers: Whether trackers list is needed
            need_properties: Whether properties dict is needed

        Returns:
            Dict with 'files', 'trackers', 'properties' keys
        """
        torrent_hash = torrent_hash.lower()
        current_time = time.time()

        with self._lock:
            # Check if we have valid cached data
            if torrent_hash in self._detail_cache:
                cached = self._detail_cache[torrent_hash]
                age = current_time - cached.get('timestamp', 0)

                # Check if cache is still valid (within TTL) AND has what we need
                if age < self._detail_cache_ttl:
                    has_what_we_need = (
                        (not need_files or cached.get('has_files', False)) and
                        (not need_trackers or cached.get('has_trackers', False)) and
                        (not need_properties or cached.get('has_properties', False))
                    )

                    if has_what_we_need:
                        # Cache hit - served from cache, no API call
                        parts = []
                        if need_files: parts.append('files')
                        if need_trackers: parts.append('trackers')
                        if need_properties: parts.append('properties')
                        log_debug(f"[CACHE HIT] {torrent_hash[:8]}... - {', '.join(parts)} (age: {age:.1f}s)")
                        return {
                            'files': cached.get('files', []) if need_files else [],
                            'trackers': cached.get('trackers', []) if need_trackers else [],
                            'properties': cached.get('properties', {}) if need_properties else {}
                        }
                    else:
                        log_debug(f"[CACHE] Cache miss for {torrent_hash[:8]}... - doesn't have needed data (need: files={need_files}, trackers={need_trackers}, props={need_properties})")

        # Cache miss or expired - fetch from API
        parts = []
        if need_files: parts.append('files')
        if need_trackers: parts.append('trackers')
        if need_properties: parts.append('properties')
        log_debug(f"[API CALL] {torrent_hash[:8]}... - Fetching {', '.join(parts)} from qBittorrent")

        result = {}

        if need_files:
            result['files'] = self.qbt_client.get_torrent_files(torrent_hash)
            result['has_files'] = True
        else:
            result['files'] = []
            result['has_files'] = False

        if need_trackers:
            result['trackers'] = self.qbt_client.get_torrent_trackers(torrent_hash)
            result['has_trackers'] = True
        else:
            result['trackers'] = []
            result['has_trackers'] = False

        if need_properties:
            result['properties'] = self.qbt_client.get_torrent_properties(torrent_hash)
            result['has_properties'] = True
        else:
            result['properties'] = {}
            result['has_properties'] = False

        # Update cache - merge with existing cache to preserve previously fetched data
        with self._lock:
            if torrent_hash not in self._detail_cache:
                self._detail_cache[torrent_hash] = {}

            # Only update the parts we actually fetched
            if need_files:
                self._detail_cache[torrent_hash]['files'] = result['files']
                self._detail_cache[torrent_hash]['has_files'] = True
            if need_trackers:
                self._detail_cache[torrent_hash]['trackers'] = result['trackers']
                self._detail_cache[torrent_hash]['has_trackers'] = True
            if need_properties:
                self._detail_cache[torrent_hash]['properties'] = result['properties']
                self._detail_cache[torrent_hash]['has_properties'] = True

            self._detail_cache[torrent_hash]['timestamp'] = current_time

        return result

    def invalidate_torrent_details(self, torrent_hash: str):
        """Invalidate cached details for a torrent (called after modifications)"""
        torrent_hash = torrent_hash.lower()
        with self._lock:
            if torrent_hash in self._detail_cache:
                log_debug(f"[CACHE] Invalidating details cache for {torrent_hash[:8]}...")
                del self._detail_cache[torrent_hash]

    def clear_detail_cache(self):
        """Clear all cached torrent details"""
        with self._lock:
            log_debug(f"[CACHE] Clearing all detail cache ({len(self._detail_cache)} entries)")
            self._detail_cache.clear()
