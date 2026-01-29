"""Main application window."""

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.api import SunoAPI
from core.cookies import get_cookie_status, get_suno_cookies
from models.track import Track
from ui.track_list import TrackListWidget


class PlaylistLoaderThread(QThread):
    """Background thread for loading playlist."""

    finished = Signal(list, str)  # tracks, error

    def __init__(self, api: SunoAPI, playlist_url: str):
        super().__init__()
        self.api = api
        self.playlist_url = playlist_url

    def run(self):
        tracks, error = self.api.get_playlist(self.playlist_url)
        self.finished.emit(tracks, error or "")


class BrowserLoaderThread(QThread):
    """Background thread for loading playlist via browser scraping."""

    progress = Signal(str)  # status message
    finished = Signal(list, str)  # tracks, error

    def __init__(self, playlist_url: str):
        super().__init__()
        self.playlist_url = playlist_url

    def run(self):
        from core.browser_scraper import scrape_playlist
        tracks, error = scrape_playlist(self.playlist_url, on_progress=self._on_progress)
        self.finished.emit(tracks, error or "")

    def _on_progress(self, msg: str):
        self.progress.emit(msg)


class DownloadThread(QThread):
    """Background thread for downloading tracks."""

    progress = Signal(int, int, str)  # current, total, current_track_name
    track_done = Signal(str, bool, str)  # track_id, success, message
    finished = Signal(int, int)  # success_count, fail_count

    def __init__(self, api: SunoAPI, tracks: list[Track], output_dir: Path):
        super().__init__()
        self.api = api
        self.tracks = tracks
        self.output_dir = output_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        success_count = 0
        fail_count = 0
        total = len(self.tracks)

        for i, track in enumerate(self.tracks):
            if self._cancelled:
                break

            self.progress.emit(i, total, track.title)

            path, error = self.api.download_track(track, self.output_dir)

            if path:
                success_count += 1
                self.track_done.emit(track.id, True, str(path))
            else:
                fail_count += 1
                self.track_done.emit(track.id, False, error or "Unknown error")

        self.progress.emit(total, total, "")
        self.finished.emit(success_count, fail_count)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Suno Downloader")
        self.setMinimumSize(500, 600)

        self.api: SunoAPI | None = None
        self.loader_thread: PlaylistLoaderThread | None = None
        self.browser_loader_thread: BrowserLoaderThread | None = None
        self.download_thread: DownloadThread | None = None

        self._setup_ui()
        self._refresh_cookies()

    def _setup_ui(self):
        """Set up the user interface."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)

        # Cookie status section
        cookie_layout = QHBoxLayout()
        self.cookie_status = QLabel("Checking cookies...")
        self.cookie_status.setStyleSheet("font-weight: bold;")
        cookie_layout.addWidget(self.cookie_status)
        cookie_layout.addStretch()

        self.refresh_btn = QPushButton("Refresh Cookies")
        self.refresh_btn.clicked.connect(self._refresh_cookies)
        cookie_layout.addWidget(self.refresh_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_all)
        cookie_layout.addWidget(self.clear_btn)
        layout.addLayout(cookie_layout)

        # Separator
        layout.addWidget(self._separator())

        # URL section (playlist or song)
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("suno.com/me, playlist, workspace, @username, or song")
        self.url_input.returnPressed.connect(self._load_playlist)
        url_layout.addWidget(self.url_input)

        self.load_btn = QPushButton("Load")
        self.load_btn.clicked.connect(self._load_playlist)
        url_layout.addWidget(self.load_btn)

        self.browser_load_btn = QPushButton("Browser Load")
        self.browser_load_btn.setToolTip("Load all tracks by opening browser (for large playlists)")
        self.browser_load_btn.clicked.connect(self._load_via_browser)
        url_layout.addWidget(self.browser_load_btn)

        self.browser_login_btn = QPushButton("Login")
        self.browser_login_btn.setToolTip("Open browser to log into Suno (saves session for Browser Load)")
        self.browser_login_btn.clicked.connect(self._open_browser_login)
        url_layout.addWidget(self.browser_login_btn)
        layout.addLayout(url_layout)

        # Separator
        layout.addWidget(self._separator())

        # Selection controls
        select_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all)
        select_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        select_layout.addWidget(self.deselect_all_btn)

        select_layout.addStretch()

        self.selection_label = QLabel("0 selected")
        select_layout.addWidget(self.selection_label)
        layout.addLayout(select_layout)

        # Track list
        self.track_list = TrackListWidget()
        self.track_list.selection_changed.connect(self._on_selection_changed)
        layout.addWidget(self.track_list, 1)

        # Separator
        layout.addWidget(self._separator())

        # Output directory
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output:"))
        self.output_input = QLineEdit()
        default_output = Path.home() / "Music" / "Suno"
        self.output_input.setText(str(default_output))
        output_layout.addWidget(self.output_input)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse_output)
        output_layout.addWidget(self.browse_btn)
        layout.addLayout(output_layout)

        # Download button
        self.download_btn = QPushButton("Download Selected")
        self.download_btn.clicked.connect(self._start_download)
        self.download_btn.setStyleSheet("padding: 10px; font-weight: bold;")
        layout.addWidget(self.download_btn)

        # Progress section
        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Initial state
        self._set_ui_enabled(False)

    def _separator(self) -> QWidget:
        """Create a horizontal separator line."""
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #ccc;")
        return line

    def _set_ui_enabled(self, enabled: bool):
        """Enable/disable UI controls."""
        self.load_btn.setEnabled(enabled)
        self.browser_load_btn.setEnabled(True)  # Browser load always available
        self.url_input.setEnabled(True)
        has_tracks = self.track_list.count() > 0
        self.select_all_btn.setEnabled(has_tracks)
        self.deselect_all_btn.setEnabled(has_tracks)
        self.download_btn.setEnabled(enabled and has_tracks)

    def _clear_all(self):
        """Clear loaded tracks and reset UI."""
        self.url_input.clear()
        self.track_list.clear()
        self.selection_label.setText("0 selected")
        self.progress_label.setText("")
        self._set_ui_enabled(self.api is not None)

    def _refresh_cookies(self):
        """Refresh cookie status."""
        found, message = get_cookie_status()

        if found:
            self.cookie_status.setText(f"✓ {message}")
            self.cookie_status.setStyleSheet("color: green; font-weight: bold;")
            cookie = get_suno_cookies()
            if cookie:
                self.api = SunoAPI(cookie)
                self._set_ui_enabled(True)
        else:
            self.cookie_status.setText(f"✗ {message}")
            self.cookie_status.setStyleSheet("color: red; font-weight: bold;")
            self.api = None
            self._set_ui_enabled(False)

    def _load_playlist(self):
        """Load playlist from URL."""
        url = self.url_input.text().strip()
        if not url:
            return

        if not self.api:
            QMessageBox.warning(self, "Error", "No cookies available")
            return

        self.load_btn.setEnabled(False)
        self.load_btn.setText("Loading...")
        self.track_list.clear()
        self.selection_label.setText("0 selected")

        self.loader_thread = PlaylistLoaderThread(self.api, url)
        self.loader_thread.finished.connect(self._on_playlist_loaded)
        self.loader_thread.start()

    @Slot(list, str)
    def _on_playlist_loaded(self, tracks: list, error: str):
        """Handle playlist load completion."""
        self.load_btn.setEnabled(True)
        self.load_btn.setText("Load")

        if error:
            QMessageBox.warning(self, "Error", f"Failed to load playlist:\n{error}")
            return

        if not tracks:
            QMessageBox.information(self, "Info", "No tracks found in playlist")
            return

        self.track_list.set_tracks(tracks)
        self._set_ui_enabled(True)

    def _open_browser_login(self):
        """Open browser for user to log into Suno."""
        from core.browser_scraper import open_browser_for_login
        self.browser_login_btn.setEnabled(False)
        self.browser_login_btn.setText("Browser open...")
        self.progress_label.setText("Log into Suno in the browser, then close it")

        # Run in thread to not block UI
        import threading
        def do_login():
            try:
                open_browser_for_login()
            finally:
                # Re-enable button (need to use signal for thread safety)
                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self.browser_login_btn, "setText",
                    Qt.ConnectionType.QueuedConnection, Q_ARG(str, "Login")
                )
                QMetaObject.invokeMethod(
                    self.browser_login_btn, "setEnabled",
                    Qt.ConnectionType.QueuedConnection, Q_ARG(bool, True)
                )
                QMetaObject.invokeMethod(
                    self.progress_label, "setText",
                    Qt.ConnectionType.QueuedConnection, Q_ARG(str, "")
                )

        threading.Thread(target=do_login, daemon=True).start()

    def _load_via_browser(self):
        """Load playlist using browser scraping (for large playlists)."""
        url = self.url_input.text().strip()
        if not url:
            return

        # Ensure it's a full URL
        if not url.startswith("http"):
            url = f"https://suno.com/{url.lstrip('/')}"

        self.browser_load_btn.setEnabled(False)
        self.load_btn.setEnabled(False)
        self.browser_load_btn.setText("Loading...")
        self.progress_label.setText("Opening browser...")
        self.track_list.clear()
        self.selection_label.setText("0 selected")

        self.browser_loader_thread = BrowserLoaderThread(url)
        self.browser_loader_thread.progress.connect(self._on_browser_progress)
        self.browser_loader_thread.finished.connect(self._on_browser_loaded)
        self.browser_loader_thread.start()

    @Slot(str)
    def _on_browser_progress(self, msg: str):
        """Handle browser loading progress."""
        self.progress_label.setText(msg)

    @Slot(list, str)
    def _on_browser_loaded(self, tracks: list, error: str):
        """Handle browser load completion."""
        self.browser_load_btn.setEnabled(True)
        self.load_btn.setEnabled(self.api is not None)
        self.browser_load_btn.setText("Browser Load")
        self.progress_label.setText("")

        if error:
            QMessageBox.warning(self, "Error", f"Failed to load:\n{error}")
            return

        if not tracks:
            QMessageBox.information(self, "Info", "No tracks found")
            return

        self.track_list.set_tracks(tracks)
        self._set_ui_enabled(True)

    def _select_all(self):
        """Select all tracks."""
        self.track_list.select_all()

    def _deselect_all(self):
        """Deselect all tracks."""
        self.track_list.deselect_all()

    @Slot(int)
    def _on_selection_changed(self, count: int):
        """Handle selection count change."""
        total = self.track_list.count()
        self.selection_label.setText(f"{count} of {total} selected")
        self.download_btn.setEnabled(count > 0 and self.api is not None)

    def _browse_output(self):
        """Open folder browser for output directory."""
        current = self.output_input.text()
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", current
        )
        if folder:
            self.output_input.setText(folder)

    def _start_download(self):
        """Start downloading selected tracks."""
        if not self.api:
            return

        tracks = self.track_list.get_selected_tracks()
        if not tracks:
            return

        output_dir = Path(self.output_input.text())
        output_dir.mkdir(parents=True, exist_ok=True)

        # Disable UI during download
        self.download_btn.setEnabled(False)
        self.download_btn.setText("Downloading...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(tracks))
        self.progress_bar.setValue(0)

        self.download_thread = DownloadThread(self.api, tracks, output_dir)
        self.download_thread.progress.connect(self._on_download_progress)
        self.download_thread.finished.connect(self._on_download_finished)
        self.download_thread.start()

    @Slot(int, int, str)
    def _on_download_progress(self, current: int, total: int, track_name: str):
        """Handle download progress update."""
        self.progress_bar.setValue(current)
        if track_name:
            self.progress_label.setText(f"Downloading: {track_name}")
        else:
            self.progress_label.setText("")

    @Slot(int, int)
    def _on_download_finished(self, success: int, failed: int):
        """Handle download completion."""
        self.download_btn.setEnabled(True)
        self.download_btn.setText("Download Selected")
        self.progress_bar.setVisible(False)
        self.progress_label.setText("")

        if failed == 0:
            QMessageBox.information(
                self, "Complete",
                f"Successfully downloaded {success} tracks!"
            )
        else:
            QMessageBox.warning(
                self, "Complete",
                f"Downloaded {success} tracks.\n{failed} failed."
            )

    def closeEvent(self, event):
        """Handle window close."""
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.download_thread.wait()
        event.accept()
