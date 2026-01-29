"""Track list widget with checkboxes for selection."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from models.track import Track


class TrackListWidget(QListWidget):
    """List widget displaying tracks with checkboxes."""

    selection_changed = Signal(int)  # Emits count of selected tracks

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: list[Track] = []
        self.itemChanged.connect(self._on_item_changed)

    def set_tracks(self, tracks: list[Track]) -> None:
        """Populate the list with tracks."""
        self.blockSignals(True)
        self.clear()
        self._tracks = tracks

        for track in tracks:
            item = QListWidgetItem(str(track))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)  # Default to selected
            item.setData(Qt.UserRole, track)
            self.addItem(item)

        self.blockSignals(False)
        self.selection_changed.emit(self.get_selected_count())

    def get_tracks(self) -> list[Track]:
        """Get all tracks."""
        return self._tracks.copy()

    def get_selected_tracks(self) -> list[Track]:
        """Get list of selected tracks."""
        selected = []
        for i in range(self.count()):
            item = self.item(i)
            if item.checkState() == Qt.Checked:
                track = item.data(Qt.UserRole)
                if track:
                    selected.append(track)
        return selected

    def get_selected_count(self) -> int:
        """Get count of selected tracks."""
        count = 0
        for i in range(self.count()):
            if self.item(i).checkState() == Qt.Checked:
                count += 1
        return count

    def select_all(self) -> None:
        """Select all tracks."""
        self.blockSignals(True)
        for i in range(self.count()):
            self.item(i).setCheckState(Qt.Checked)
        self.blockSignals(False)
        self.selection_changed.emit(self.get_selected_count())

    def deselect_all(self) -> None:
        """Deselect all tracks."""
        self.blockSignals(True)
        for i in range(self.count()):
            self.item(i).setCheckState(Qt.Unchecked)
        self.blockSignals(False)
        self.selection_changed.emit(0)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Handle item checkbox state change."""
        self.selection_changed.emit(self.get_selected_count())
