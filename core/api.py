"""Suno API client for fetching playlists and downloading tracks."""

import json
import re
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests

from models.track import Track


class SunoAPI:
    """Client for interacting with Suno's API."""

    def __init__(self, cookie: str):
        self.cookie = cookie
        self.base_url = "https://studio-api.suno.ai"
        self.session = requests.Session()
        self.session.headers.update({
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Origin": "https://suno.com",
            "Referer": "https://suno.com/",
        })

    def extract_playlist_id(self, url: str) -> str | None:
        """Extract playlist ID from URL."""
        match = re.search(r"playlist/([a-f0-9-]{36})", url)
        return match.group(1) if match else None

    def extract_song_id(self, url: str) -> str | None:
        """Extract song ID from URL."""
        match = re.search(r"song/([a-f0-9-]{36})", url)
        return match.group(1) if match else None

    def extract_profile(self, url: str) -> str | None:
        """Extract profile handle from URL (@username or /me)."""
        if "/me" in url or url.endswith("/me"):
            return "me"
        match = re.search(r"@([a-zA-Z0-9_-]+)", url)
        return match.group(1) if match else None

    def extract_workspace_id(self, url: str) -> str | None:
        """Extract workspace ID from URL (/create?wid=...)."""
        match = re.search(r"wid=([a-f0-9-]{36})", url)
        return match.group(1) if match else None

    def get_tracks(self, url: str) -> tuple[list[Track], str | None]:
        """
        Fetch tracks from a playlist, profile/library, or single song URL.

        Args:
            url: Playlist URL, profile URL (@user or /me), song URL, or just an ID

        Returns:
            Tuple of (tracks list, error message or None)
        """
        # Check if it's a song URL
        song_id = self.extract_song_id(url)
        if song_id:
            return self._fetch_single_song(song_id)

        # Check if it's a workspace URL
        workspace_id = self.extract_workspace_id(url)
        if workspace_id:
            return self._fetch_workspace(workspace_id)

        # Check if it's a profile/library URL
        profile = self.extract_profile(url)
        if profile:
            return self._fetch_library(profile)

        # Check if it's a playlist URL
        playlist_id = self.extract_playlist_id(url)
        if playlist_id:
            return self._fetch_playlist(playlist_id)

        # Maybe it's just an ID - try both
        if re.match(r"^[a-f0-9-]{36}$", url):
            # Try as song first (faster), then playlist
            tracks, error = self._fetch_single_song(url)
            if tracks:
                return tracks, None
            return self._fetch_playlist(url)

        return [], "Invalid URL (use playlist, @username, /me, or song URL)"

    def get_playlist(self, playlist_url: str) -> tuple[list[Track], str | None]:
        """Fetch tracks - supports both playlist and song URLs."""
        return self.get_tracks(playlist_url)

    def _fetch_single_song(self, song_id: str) -> tuple[list[Track], str | None]:
        """Fetch a single song by ID."""
        try:
            url = f"https://suno.com/song/{song_id}"
            resp = self.session.get(url, timeout=15)

            if resp.status_code != 200:
                return [], f"HTTP {resp.status_code}"

            html = resp.text

            # Extract title from og:title
            title = "Untitled"
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if title_match:
                title = title_match.group(1)

            # Extract audio URL from og:audio
            audio_match = re.search(r'<meta property="og:audio" content="([^"]+)"', html)
            if not audio_match:
                return [], "Could not find audio URL"

            audio_url = audio_match.group(1)

            track = Track(
                id=song_id,
                title=title,
                audio_url=audio_url,
            )

            return [track], None

        except Exception as e:
            return [], str(e)

    def _fetch_workspace(self, workspace_id: str) -> tuple[list[Track], str | None]:
        """Fetch tracks from a workspace."""
        endpoints = [
            f"{self.base_url}/api/workspace/{workspace_id}",
            f"{self.base_url}/api/workspace/{workspace_id}/clips",
            f"https://suno.com/api/workspace/{workspace_id}",
        ]

        for endpoint in endpoints:
            try:
                resp = self.session.get(endpoint, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    tracks = self._parse_api_response(data)
                    if tracks:
                        return tracks, None
            except Exception:
                continue

        # Workspace API might not be accessible - suggest browser load
        return [], "Workspace API not accessible. Try 'Browser Load' instead."

    def _fetch_library(self, profile: str) -> tuple[list[Track], str | None]:
        """Fetch all tracks from user's library with pagination."""
        all_tracks = []
        page = 1

        # Try feed/library API endpoints
        if profile == "me":
            endpoints = [
                f"{self.base_url}/api/feed",
                f"{self.base_url}/api/feed/v2",
            ]
        else:
            endpoints = [
                f"{self.base_url}/api/user/{profile}/songs",
                f"https://suno.com/api/profiles/{profile}",
            ]

        for endpoint in endpoints:
            try:
                page = 1
                all_tracks = []

                while True:
                    params = {"page": page}
                    resp = self.session.get(endpoint, params=params, timeout=30)

                    if resp.status_code != 200:
                        break

                    data = resp.json()
                    tracks = self._parse_api_response(data)

                    if not tracks:
                        if all_tracks:
                            return all_tracks, None
                        break

                    all_tracks.extend(tracks)

                    # Check for more pages
                    if len(tracks) < 20:  # Typical page size
                        break

                    page += 1
                    if page > 50:  # Safety limit
                        break

                if all_tracks:
                    return all_tracks, None

            except Exception:
                continue

        return [], f"Could not fetch library for {profile}"

    def _fetch_playlist(self, playlist_id: str) -> tuple[list[Track], str | None]:
        """Fetch tracks from a playlist."""
        # Try the API endpoint first
        tracks, error = self._fetch_via_api(playlist_id)
        if tracks:
            return tracks, None

        # Fallback: parse the HTML page for embedded data
        tracks, error = self._fetch_via_html(playlist_id)
        if tracks:
            return tracks, None

        return [], error or "Failed to fetch playlist"

    def _fetch_via_api(self, playlist_id: str) -> tuple[list[Track], str | None]:
        """Try fetching playlist via API endpoints with pagination."""
        endpoints = [
            f"{self.base_url}/api/playlist/{playlist_id}",
            f"https://suno.com/api/playlist/{playlist_id}",
        ]

        for endpoint in endpoints:
            try:
                all_tracks = []
                page = 1
                page_size = 50  # Suno's typical page size

                while True:
                    params = {"page": page, "page_size": page_size}
                    resp = self.session.get(endpoint, params=params, timeout=30)
                    if resp.status_code != 200:
                        break

                    data = resp.json()
                    tracks = self._parse_api_response(data)

                    if not tracks:
                        # No more tracks or different response format
                        if all_tracks:
                            return all_tracks, None
                        break

                    all_tracks.extend(tracks)

                    # Check if we got a full page (more might exist)
                    if len(tracks) < page_size:
                        break

                    page += 1

                    # Safety limit to prevent infinite loops
                    if page > 20:  # Max 1000 tracks
                        break

                if all_tracks:
                    return all_tracks, None

            except Exception:
                continue

        return [], "API endpoints not accessible"

    def _fetch_via_html(self, playlist_id: str) -> tuple[list[Track], str | None]:
        """Fallback: parse the playlist HTML page for embedded JSON data."""
        try:
            url = f"https://suno.com/playlist/{playlist_id}"
            resp = self.session.get(url, timeout=30)

            if resp.status_code != 200:
                return [], f"HTTP {resp.status_code}"

            html = resp.text

            # Look for __NEXT_DATA__ script tag (Next.js apps embed data here)
            match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>',
                html,
                re.DOTALL
            )

            if match:
                data = json.loads(match.group(1))
                tracks = self._parse_nextjs_data(data)
                if tracks:
                    return tracks, None

            # Alternative: look for JSON in script tags
            matches = re.findall(r'"clips":\s*(\[[^\]]+\])', html)
            for match in matches:
                try:
                    clips = json.loads(match)
                    tracks = self._parse_clips(clips)
                    if tracks:
                        return tracks, None
                except json.JSONDecodeError:
                    continue

            # Fallback: extract from og:audio meta tags
            tracks = self._parse_meta_audio_tags(html)
            if tracks:
                return tracks, None

            return [], "Could not find track data in page"

        except Exception as e:
            return [], str(e)

    def _parse_meta_audio_tags(self, html: str) -> list[Track]:
        """Extract tracks from og:audio meta tags and fetch titles."""
        tracks = []

        # Find all og:audio URLs
        audio_urls = re.findall(r'<meta property="og:audio" content="([^"]+)"', html)

        for i, audio_url in enumerate(audio_urls):
            # Extract track ID from URL like https://cdn1.suno.ai/UUID.mp3
            match = re.search(r'/([a-f0-9-]{36})\.mp3', audio_url)
            if match:
                track_id = match.group(1)
                # Try to get title from song page
                title = self._fetch_track_title(track_id) or f"Track {i + 1}"
                tracks.append(Track(
                    id=track_id,
                    title=title,
                    audio_url=audio_url,
                ))

        return tracks

    def _fetch_track_title(self, track_id: str) -> str | None:
        """Fetch track title from song page."""
        try:
            url = f"https://suno.com/song/{track_id}"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                # Extract og:title
                match = re.search(r'<meta property="og:title" content="([^"]+)"', resp.text)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    def _parse_api_response(self, data: dict) -> list[Track]:
        """Parse API response into Track objects."""
        tracks = []

        # Handle various response formats
        clips = data.get("clips") or data.get("playlist_clips") or data.get("items") or []

        if isinstance(data, list):
            clips = data

        for clip in clips:
            track = self._parse_clip(clip)
            if track:
                tracks.append(track)

        return tracks

    def _parse_nextjs_data(self, data: dict) -> list[Track]:
        """Parse Next.js __NEXT_DATA__ JSON."""
        tracks = []

        try:
            # Navigate the Next.js data structure
            props = data.get("props", {})
            page_props = props.get("pageProps", {})

            # Try various possible locations
            playlist = page_props.get("playlist", {})
            clips = (
                playlist.get("playlist_clips", []) or
                playlist.get("clips", []) or
                page_props.get("clips", [])
            )

            for item in clips:
                # playlist_clips often have nested clip object
                clip = item.get("clip", item)
                track = self._parse_clip(clip)
                if track:
                    tracks.append(track)

        except Exception:
            pass

        return tracks

    def _parse_clips(self, clips: list) -> list[Track]:
        """Parse a list of clip objects."""
        tracks = []
        for clip in clips:
            track = self._parse_clip(clip)
            if track:
                tracks.append(track)
        return tracks

    def _parse_clip(self, clip: dict) -> Track | None:
        """Parse a single clip object into a Track."""
        if not isinstance(clip, dict):
            return None

        clip_id = clip.get("id")
        title = clip.get("title") or clip.get("name") or "Untitled"
        audio_url = clip.get("audio_url") or clip.get("song_path")

        if not clip_id or not audio_url:
            return None

        return Track(
            id=clip_id,
            title=title,
            audio_url=audio_url,
            duration=clip.get("duration"),
            artist=clip.get("display_name") or clip.get("handle"),
            image_url=clip.get("image_url") or clip.get("image_large_url"),
        )

    def download_track(
        self,
        track: Track,
        output_dir: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[Path | None, str | None]:
        """
        Download a track to the output directory.

        Args:
            track: Track to download
            output_dir: Directory to save the file
            progress_callback: Optional callback(bytes_downloaded, total_bytes)

        Returns:
            Tuple of (file path or None, error message or None)
        """
        try:
            # Sanitize filename
            safe_title = self._sanitize_filename(track.title)
            filename = f"{safe_title} - {track.id}.mp3"
            output_path = output_dir / filename

            # Download with streaming
            resp = self.session.get(track.audio_url, stream=True, timeout=60)
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

            return output_path, None

        except Exception as e:
            return None, str(e)

    def _sanitize_filename(self, name: str) -> str:
        """Remove invalid filename characters."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")
        # Limit length
        return name[:100].strip()


if __name__ == "__main__":
    # Test API client
    from core.cookies import get_suno_cookies

    cookie = get_suno_cookies()
    if not cookie:
        print("No cookies found")
        exit(1)

    api = SunoAPI(cookie)
    tracks, error = api.get_playlist("8fde6632-d1eb-4d4e-b8ae-79b9d5753ecc")

    if error:
        print(f"Error: {error}")
    else:
        print(f"Found {len(tracks)} tracks:")
        for t in tracks[:5]:
            print(f"  - {t.title} ({t.id})")
