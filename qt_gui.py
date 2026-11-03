"""Qt interface for the offline Syntec program combiner."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)


STYLE = """
QWidget { color: #17283b; font-family: "Segoe UI"; font-size: 10pt; }
QMainWindow, QWidget#page { background: #f1f5f9; }
QFrame#card { background: white; border: 1px solid #dce5ee; border-radius: 10px; }
QLabel#title { font-size: 22pt; font-weight: 700; color: #102b46; }
QLabel#subtitle { color: #52677b; font-size: 10pt; }
QLabel#section { color: #355069; font-size: 9pt; font-weight: 700; }
QLabel#hint { color: #607387; font-size: 9pt; }
QLabel#warning { background: #fff6df; color: #6a4b13; border: 1px solid #efdaaa;
                 border-radius: 6px; padding: 10px; }
QLineEdit { background: #fbfdff; border: 1px solid #b9c9d8; border-radius: 5px;
            padding: 8px; selection-background-color: #2265a4; }
QLineEdit:focus { border: 2px solid #2c75b7; padding: 7px; }
QPushButton { background: white; border: 1px solid #acbfd1; border-radius: 5px;
              padding: 8px 16px; font-weight: 600; }
QPushButton:hover { background: #eaf2f9; }
QPushButton#primary { background: #1762a1; border: 1px solid #1762a1; color: white;
                      padding: 10px 20px; }
QPushButton#primary:hover { background: #104e84; }
QCheckBox { spacing: 8px; }
"""


class InputFileEdit(QLineEdit):
    selection_attempted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Drop one file here or use Browse")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        self.selection_attempted.emit()
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            self.clear()
            QMessageBox.warning(self, "File drop failed", "Drop exactly one local file into this field.")
            event.acceptProposedAction()
            return
        path = Path(urls[0].toLocalFile())
        if not path.is_file():
            self.clear()
            QMessageBox.warning(self, "File drop failed",
                                "Drop an existing file, not a folder or an unavailable path.")
            event.acceptProposedAction()
            return
        self.setText(str(path))
        event.acceptProposedAction()


class CombinerWindow(QMainWindow):
    def __init__(self, create_file, program_error):
        super().__init__()
        self.create_file = create_file
        self.program_error = program_error
        self.setWindowTitle("Syntec offline program combiner")
        self.resize(800, 620)
        self.setMinimumWidth(600)

        page = QWidget(objectName="page")
        self.setCentralWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        title = QLabel("Syntec Program Combiner", objectName="title")
        subtitle = QLabel("Prepare a loading + unloading transition program offline.", objectName="subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame(objectName="card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(10)
        layout.addWidget(card)

        self.load = InputFileEdit()
        self.unload = InputFileEdit()
        self.output = QLineEdit()
        self.output.setAcceptDrops(False)
        self.output.setPlaceholderText("Choose a new output file")
        self.number = QLineEdit()
        self.number.setPlaceholderText("Unused O number, 1-9999")
        self.number.setMaximumWidth(240)
        self.confirmed = QCheckBox("I verified the shared physical tools and offsets match.")

        self._file_row(card_layout, "LOADING / OP 1", "G54 - G57", self.load, False)
        self._file_row(card_layout, "UNLOADING / OP 2", "G58, G59, G54 P7, G54 P8", self.unload, False)
        self._file_row(card_layout, "NEW OUTPUT FILE", "A new file; inputs are never overwritten", self.output, True)
        card_layout.addWidget(QLabel("NEW O NUMBER", objectName="section"))
        card_layout.addWidget(self.number)
        card_layout.addSpacing(2)
        card_layout.addWidget(self.confirmed)
        for field in (self.load, self.unload):
            field.textChanged.connect(self._reset_confirmation)
            field.selection_attempted.connect(self._reset_confirmation)

        warning = QLabel("Before cutting: independently verify the program, tool setup, offsets and transitions; "
                         "simulate and perform a cautious dry run.", objectName="warning")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        actions = QHBoxLayout()
        actions.addStretch()
        self.create_button = QPushButton("Create combined program", objectName="primary")
        self.create_button.clicked.connect(self._create)
        actions.addWidget(self.create_button)
        layout.addLayout(actions)
        layout.addStretch()

    def _file_row(self, layout, title, hint, field, save):
        heading = QHBoxLayout()
        heading.addWidget(QLabel(title, objectName="section"))
        heading.addStretch()
        heading.addWidget(QLabel(hint, objectName="hint"))
        layout.addLayout(heading)
        row = QHBoxLayout()
        row.addWidget(field, 1)
        button = QPushButton("Browse")
        button.clicked.connect(lambda: self._browse(field, save))
        row.addWidget(button)
        layout.addLayout(row)
        layout.addSpacing(3)

    def _reset_confirmation(self, *_):
        self.confirmed.setChecked(False)

    def _browse(self, field, save):
        filters = "NC files (*.nc);;All files (*)"
        if save:
            path, _ = QFileDialog.getSaveFileName(self, "Choose new output file", "", filters)
            if path and not Path(path).suffix:
                path += ".nc"
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select program", "", filters)
        if path:
            if not save:
                self._reset_confirmation()
            field.setText(str(Path(path)))

    def _create(self):
        try:
            if not self.confirmed.isChecked():
                raise self.program_error("Confirm that shared physical tools and offsets match first.")
            values = [field.text().strip() for field in (self.load, self.unload, self.output, self.number)]
            if not all(values):
                raise self.program_error("Select both inputs, an output file, and a new O number.")
            if not values[3].isdigit():
                raise self.program_error("The new O number must contain digits only.")
            _, _, order = self.create_file(Path(values[0]), Path(values[1]), Path(values[2]), int(values[3]))
        except self.program_error as exc:
            QMessageBox.critical(self, "No combined program created", str(exc))
            return
        QMessageBox.information(self, "Program created",
                                f"Tool order: {', '.join('T' + str(tool) for tool in order)}\n\n"
                                "Verify tool setup and offsets, simulate, and dry run before cutting.")


def run_gui(create_file, program_error):
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = CombinerWindow(create_file, program_error)
    window.show()
    return app.exec()
