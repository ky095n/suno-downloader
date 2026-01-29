"""Browser-based scraper using Playwright to load all tracks via scrolling."""

import json
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from models.track import Track


def get_chrome_user_data_dir() -> Path:
    """Get Chrome's user data directory."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    return Path(local_app_data) / "Google" / "Chrome" / "User Data"


def get_browser_data_dir() -> Path:
    """Get the persistent browser data directory."""
    user_data_dir = Path.home() / ".suno-downloader" / "browser-data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return user_data_dir


def open_browser_for_login():
    """Open browser to Suno for user to log in. Session will be saved."""
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(get_browser_data_dir()),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://suno.com/me", wait_until="load", timeout=60000)

        # Wait for user to close the browser
        try:
            while True:
                page.wait_for_timeout(1000)
        except Exception:
            pass  # Browser was closed

        context.close()


def scrape_playlist(playlist_url: str, on_progress=None) -> tuple[list[Track], str | None]:
    """
    Scrape all tracks from a Suno playlist by scrolling through it.

    Args:
        playlist_url: Full URL to the playlist
        on_progress: Optional callback(message) for progress updates

    Returns:
        Tuple of (tracks list, error message or None)
    """
    tracks_data = {}  # Use dict to dedupe by ID

    def log(msg):
        if on_progress:
            on_progress(msg)
        print(msg)

    def handle_response(response):
        """Intercept API responses to capture track data."""
        url = response.url

        # Look for any API responses that might contain tracks
        track_endpoints = ["playlist", "feed", "clips", "songs", "profile", "me", "user", "library", "workspace", "create"]
        if any(ep in url for ep in track_endpoints) and response.status == 200:
            try:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    data = response.json()
                    extract_tracks(data)
            except Exception:
                pass

    def extract_tracks(data):
        """Extract tracks from API response data."""
        if isinstance(data, dict):
            # Check for clips array
            clips = data.get("playlist_clips") or data.get("clips") or data.get("items") or []
            for item in clips:
                clip = item.get("clip", item) if isinstance(item, dict) else item
                add_track(clip)

            # Also check nested structures
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    extract_tracks(value)

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    add_track(item)
                    extract_tracks(item)

    def add_track(clip):
        """Add a track if it has the required fields."""
        if not isinstance(clip, dict):
            return

        clip_id = clip.get("id")
        audio_url = clip.get("audio_url") or clip.get("song_path")
        title = clip.get("title") or clip.get("name")

        if clip_id and audio_url and clip_id not in tracks_data:
            tracks_data[clip_id] = {
                "id": clip_id,
                "title": title or "Untitled",
                "audio_url": audio_url,
                "duration": clip.get("duration"),
                "artist": clip.get("display_name") or clip.get("handle"),
                "image_url": clip.get("image_url") or clip.get("image_large_url"),
            }

    try:
        with sync_playwright() as p:
            log("Launching browser...")

            # Use persistent context to remember login
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(get_browser_data_dir()),
                headless=False,  # Show browser so user can see/login
                viewport={"width": 1280, "height": 800},
                args=["--disable-blink-features=AutomationControlled"],
            )

            # Use existing page or create new one
            page = context.pages[0] if context.pages else context.new_page()

            # Intercept responses
            page.on("response", handle_response)

            log(f"Loading {playlist_url}...")
            page.goto(playlist_url, wait_until="load", timeout=60000)

            # Wait for initial content to render
            log("Waiting for content to load...")
            page.wait_for_timeout(5000)

            log("Scrolling to load all tracks...")

            # Scroll down repeatedly until no new tracks load
            last_count = 0
            no_change_count = 0
            max_scrolls = 100  # Safety limit

            for i in range(max_scrolls):
                # Use mouse wheel to scroll - position mouse in center of page
                page.mouse.move(640, 400)
                page.mouse.wheel(0, 3000)  # Large scroll delta
                page.wait_for_timeout(1500)  # Wait for content to load

                current_count = len(tracks_data)
                log(f"  Scroll {i+1}: {current_count} tracks found")

                if current_count == last_count:
                    no_change_count += 1
                    if no_change_count >= 5:
                        log("No new tracks loading, done scrolling")
                        break
                else:
                    no_change_count = 0
                    last_count = current_count

            # Also try to get any tracks from the page content
            log("Extracting tracks from page...")
            try:
                # Get page HTML and parse for audio URLs
                html = page.content()

                # Extract from embedded JSON
                json_matches = re.findall(r'\{[^{}]*"audio_url"\s*:\s*"[^"]+cdn[^"]+\.mp3"[^{}]*\}', html)
                for match in json_matches:
                    try:
                        obj = json.loads(match)
                        add_track(obj)
                    except json.JSONDecodeError:
                        pass

                # Extract audio URLs and IDs from meta tags
                og_audios = re.findall(r'<meta property="og:audio" content="([^"]+)"', html)
                for audio_url in og_audios:
                    m = re.search(r'/([a-f0-9-]{36})\.mp3', audio_url)
                    if m and m.group(1) not in tracks_data:
                        tracks_data[m.group(1)] = {
                            "id": m.group(1),
                            "title": f"Track {len(tracks_data) + 1}",
                            "audio_url": audio_url,
                        }
            except Exception as e:
                log(f"Error extracting from page: {e}")

            context.close()

    except Exception as e:
        return [], f"Browser error: {e}"

    # Convert to Track objects
    tracks = []
    for data in tracks_data.values():
        tracks.append(Track(
            id=data["id"],
            title=data["title"],
            audio_url=data["audio_url"],
            duration=data.get("duration"),
            artist=data.get("artist"),
            image_url=data.get("image_url"),
        ))

    log(f"Found {len(tracks)} total tracks")
    return tracks, None


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://suno.com/playlist/5a1b34e2-bc83-4ac8-b8e7-287854a45140"
    tracks, error = scrape_playlist(url)
    if error:
        print(f"Error: {error}")
    else:
        print(f"\nFound {len(tracks)} tracks:")
        for t in tracks[:10]:
            print(f"  - {t.title}")
        if len(tracks) > 10:
            print(f"  ... and {len(tracks) - 10} more")
