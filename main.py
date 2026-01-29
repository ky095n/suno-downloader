#!/usr/bin/env python3
"""Suno Playlist Downloader - Entry Point."""

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Suno Playlist Downloader")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
