# Suno Downloader

A desktop application to download your music from [Suno.com](https://suno.com).

## Features

- Download tracks from playlists, workspaces, profiles, or your personal library
- **Browser Load**: Automatically scrolls through large playlists/libraries to capture all tracks (no 50-track limit)
- Batch download with progress tracking
- Extracts cookies from your browser automatically (Chrome, Edge, Brave, Firefox)

## Requirements

- Python 3.10+
- Windows (cookie extraction currently Windows-only)
- A Suno.com account (logged in via your browser)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ky095n/suno-downloader.git
   cd suno-downloader
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright browser (for Browser Load feature):
   ```bash
   playwright install chromium
   ```

## Usage

1. **Log into Suno.com** in your regular browser (Chrome, Edge, etc.)

2. **Run the application**:
   ```bash
   python main.py
   ```

3. **Load tracks** using one of these methods:

   | Method | Use Case |
   |--------|----------|
   | **Load** | Quick API load (limited to ~50 tracks) |
   | **Browser Load** | Full load via browser automation (unlimited) |
   | **Login** | First-time setup for Browser Load |

4. **Enter a URL**:
   - Your library: `https://suno.com/me`
   - A playlist: `https://suno.com/playlist/[id]`
   - A workspace: `https://suno.com/create?wid=[id]`
   - A profile: `https://suno.com/@username`
   - A single song: `https://suno.com/song/[id]`

5. **Select tracks** and click **Download Selected**

### First-Time Browser Load Setup

The first time you use "Browser Load":
1. Click **Login** to open a browser window
2. Log into your Suno account
3. Close the browser
4. Now "Browser Load" will use your logged-in session

## Project Structure

```
suno-downloader/
├── main.py              # Application entry point
├── core/
│   ├── api.py           # Suno API client
│   ├── browser_scraper.py  # Playwright-based scraper
│   └── cookies.py       # Browser cookie extraction
├── models/
│   └── track.py         # Track data model
├── ui/
│   ├── main_window.py   # Main application window
│   └── track_list.py    # Track list widget
└── requirements.txt
```

## How It Works

1. **Cookie Extraction**: Reads Suno authentication cookies from your browser
2. **API Loading**: Fetches track metadata from Suno's API
3. **Browser Loading**: Uses Playwright to automate scrolling and capture all tracks from infinite-scroll pages
4. **Downloading**: Downloads MP3 files directly from Suno's CDN

## Troubleshooting

### "No cookies found"
- Make sure you're logged into Suno.com in Chrome, Edge, or another supported browser
- Close all browser windows and try "Refresh Cookies"

### Browser Load not finding tracks
- Click "Login" first to set up the browser session
- Make sure you're logged in when the browser opens

### Only getting 50 tracks
- Use "Browser Load" instead of "Load" for large playlists

## License

MIT License

## Disclaimer

This tool is for personal use to download your own music from Suno. Please respect Suno's terms of service and copyright laws.
