"""Browser cookie extraction for Suno authentication."""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import browser_cookie3


# Browser cookie paths and key files (Chromium-based browsers)
BROWSER_PATHS = {
    "slimjet": {
        "cookies": Path(os.environ.get("LOCALAPPDATA", "")) / "Slimjet/User Data/Default/Network/Cookies",
        "key": Path(os.environ.get("LOCALAPPDATA", "")) / "Slimjet/User Data/Local State",
    },
    "brave": {
        "cookies": Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware/Brave-Browser/User Data/Default/Network/Cookies",
        "key": Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware/Brave-Browser/User Data/Local State",
    },
    "chrome": {
        "cookies": Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default/Network/Cookies",
        "key": Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Local State",
    },
    "edge": {
        "cookies": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data/Default/Network/Cookies",
        "key": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data/Local State",
    },
}


def get_suno_cookies_from_file(cookie_path: Path) -> str | None:
    """
    Extract Suno cookies directly from a Chromium cookie database file.

    Args:
        cookie_path: Path to the Cookies SQLite database

    Returns:
        Cookie header string or None if not found
    """
    if not cookie_path.exists():
        return None

    # Copy to temp file to avoid lock issues
    temp_dir = tempfile.mkdtemp()
    temp_cookie = Path(temp_dir) / "Cookies"

    try:
        shutil.copy2(cookie_path, temp_cookie)

        conn = sqlite3.connect(temp_cookie)
        cursor = conn.cursor()

        # Query for suno.com cookies
        cursor.execute("""
            SELECT name, value, encrypted_value
            FROM cookies
            WHERE host_key LIKE '%suno.com%'
        """)

        cookies = []
        for name, value, encrypted_value in cursor.fetchall():
            # Try unencrypted value first
            if value:
                cookies.append(f"{name}={value}")
            # Note: encrypted_value would need DPAPI decryption on Windows
            # browser_cookie3 handles this, so we'll fall back to that

        conn.close()

        if cookies:
            return "; ".join(cookies)

    except Exception as e:
        pass
    finally:
        # Cleanup temp file
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

    return None


def get_suno_cookies(browser: str = "slimjet") -> str | None:
    """
    Extract Suno cookies from the specified browser.

    Args:
        browser: Browser to extract from ('slimjet', 'brave', 'chrome', 'edge')

    Returns:
        Cookie header string or None if not found
    """
    browsers_to_try = [browser] + [b for b in BROWSER_PATHS if b != browser]

    for browser_name in browsers_to_try:
        paths = BROWSER_PATHS.get(browser_name)
        if not paths:
            continue

        cookie_path = paths["cookies"]
        key_path = paths["key"]

        if not cookie_path.exists():
            continue

        # For Slimjet and other Chromium clones, use chrome function with custom paths
        if browser_name == "slimjet":
            try:
                cj = browser_cookie3.chrome(
                    cookie_file=str(cookie_path),
                    key_file=str(key_path) if key_path.exists() else None,
                    domain_name=".suno.com"
                )
                cookies = list(cj)
                if cookies:
                    return "; ".join(f"{c.name}={c.value}" for c in cookies)
            except Exception as e:
                pass

        # Try browser_cookie3's built-in functions
        browser_funcs = {
            "brave": browser_cookie3.brave,
            "chrome": browser_cookie3.chrome,
            "edge": browser_cookie3.edge,
        }

        func = browser_funcs.get(browser_name)
        if func:
            try:
                cj = func(domain_name=".suno.com")
                cookies = list(cj)
                if cookies:
                    return "; ".join(f"{c.name}={c.value}" for c in cookies)
            except Exception:
                continue

    return None


def get_cookie_status() -> tuple[bool, str]:
    """
    Check if Suno cookies are available.

    Returns:
        Tuple of (found: bool, message: str)
    """
    # Check which browsers have cookie files
    available_browsers = [name for name, paths in BROWSER_PATHS.items() if paths["cookies"].exists()]

    try:
        cookie = get_suno_cookies()
        if cookie:
            if "__session" in cookie or "__client" in cookie:
                return True, "Authenticated cookies found"
            return True, "Cookies found (may need login)"
    except Exception as e:
        error_msg = str(e).lower()
        if "admin" in error_msg or "permission" in error_msg:
            return False, "Close browser and try again"
        return False, f"Cookie error: {e}"

    if available_browsers:
        browsers_str = ", ".join(available_browsers)
        return False, f"No Suno cookies - log in to suno.com, close browser ({browsers_str})"
    return False, "No supported browser found"


def get_detailed_status() -> dict:
    """Get detailed cookie status for debugging."""
    result = {
        "browsers": {},
        "suno_cookies": None,
        "error": None,
    }

    for name, paths in BROWSER_PATHS.items():
        result["browsers"][name] = {
            "path": str(paths["cookies"]),
            "exists": paths["cookies"].exists(),
        }

    try:
        cookie = get_suno_cookies()
        if cookie:
            result["suno_cookies"] = {
                "length": len(cookie),
                "has_session": "__session" in cookie,
                "has_client": "__client" in cookie,
            }
    except Exception as e:
        result["error"] = str(e)

    return result


if __name__ == "__main__":
    import json

    print("=== Cookie Status ===")
    found, message = get_cookie_status()
    print(f"Found: {found}")
    print(f"Message: {message}")

    print("\n=== Detailed Status ===")
    details = get_detailed_status()
    print(json.dumps(details, indent=2))

    if found:
        cookies = get_suno_cookies()
        if cookies:
            print(f"\nCookie length: {len(cookies)} chars")
            print(f"Preview: {cookies[:100]}...")
