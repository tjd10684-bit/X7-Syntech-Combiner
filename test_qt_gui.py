import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import combiner
from test_combiner import sample


@unittest.skipUnless(os.environ.get("SYNTEC_GUI_TESTS"), "Set SYNTEC_GUI_TESTS to run Qt GUI tests.")
class QtGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from qt_gui import CombinerWindow

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.load = root / "loading \u00f1.nc"
        self.unload = root / "unload.nc"
        self.output = root / "combined.nc"
        self.load.write_text(sample(1001, combiner.LOAD_OFFSETS), encoding="ascii")
        self.unload.write_text(sample(3001, combiner.UNLOAD_OFFSETS), encoding="ascii")
        self.window = CombinerWindow(combiner.create_file, combiner.ProgramError)
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.window.close)

    def drop(self, field, urls):
        from PySide6.QtCore import QMimeData, QPointF, Qt
        from PySide6.QtGui import QDragEnterEvent, QDropEvent
        from PySide6.QtWidgets import QApplication

        mime = QMimeData()
        mime.setUrls(urls)
        enter = QDragEnterEvent(QPointF(2, 2), Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(field, enter)
        self.assertTrue(enter.isAccepted())
        event = QDropEvent(QPointF(2, 2), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(field, event)
        self.assertTrue(event.isAccepted())

    def test_drag_drop_creation_and_invalid_selections(self):
        from PySide6.QtCore import QUrl

        w = self.window
        with mock.patch("qt_gui.QMessageBox.warning") as warning, \
             mock.patch("qt_gui.QMessageBox.information") as success, \
             mock.patch("qt_gui.QMessageBox.critical") as error:
            self.drop(w.load, [QUrl.fromLocalFile(str(self.load))])
            self.drop(w.unload, [QUrl.fromLocalFile(str(self.unload))])
            self.assertEqual(w.load.text(), str(self.load))
            self.assertEqual(w.unload.text(), str(self.unload))
            w.confirmed.setChecked(True)
            self.drop(w.load, [QUrl.fromLocalFile(str(self.load))])
            self.assertFalse(w.confirmed.isChecked())
            w.confirmed.setChecked(True)
            self.drop(w.load, [QUrl.fromLocalFile(str(self.load)), QUrl.fromLocalFile(str(self.unload))])
            self.assertEqual(w.load.text(), "")
            self.assertFalse(w.confirmed.isChecked())
            self.drop(w.unload, [QUrl.fromLocalFile(str(self.unload.parent))])
            self.assertEqual(w.unload.text(), "")
            self.drop(w.unload, [QUrl.fromLocalFile(str(self.unload.parent / "missing.nc"))])
            self.assertEqual(w.unload.text(), "")
            self.drop(w.unload, [QUrl("https://example.invalid/file.nc")])
            self.assertEqual(w.unload.text(), "")
            self.assertEqual(warning.call_count, 4)
            self.drop(w.load, [QUrl.fromLocalFile(str(self.load))])
            self.drop(w.unload, [QUrl.fromLocalFile(str(self.unload))])
            w.output.setText(str(self.output))
            w.number.setText("1234")
            w.confirmed.setChecked(True)
            w.create_button.click()
        error.assert_not_called()
        success.assert_called_once()
        self.assertIn("O1234", self.output.read_text())

    def test_browse_and_confirmation_reset(self):
        w = self.window
        w.confirmed.setChecked(True)
        with mock.patch("qt_gui.QFileDialog.getOpenFileName", return_value=(str(self.load), "")):
            w._browse(w.load, False)
        self.assertEqual(w.load.text(), str(self.load))
        self.assertFalse(w.confirmed.isChecked())
        w.confirmed.setChecked(True)
        with mock.patch("qt_gui.QFileDialog.getOpenFileName", return_value=(str(self.load), "")):
            w._browse(w.load, False)
        self.assertFalse(w.confirmed.isChecked())
        w.confirmed.setChecked(True)
        with mock.patch("qt_gui.QFileDialog.getOpenFileName", return_value=("", "")):
            w._browse(w.load, False)
        self.assertTrue(w.confirmed.isChecked())
        with mock.patch("qt_gui.QFileDialog.getSaveFileName", return_value=(str(self.output.with_suffix("")), "")):
            w._browse(w.output, True)
        self.assertEqual(w.output.text(), str(self.output))
        self.assertTrue(w.confirmed.isChecked())

    def test_validation_does_not_create_output(self):
        w = self.window
        w.load.setText(str(self.load))
        w.unload.setText(str(self.unload))
        w.output.setText(str(self.output))
        w.number.setText("1234")
        with mock.patch("qt_gui.QMessageBox.critical") as error:
            w.create_button.click()
            self.assertFalse(self.output.exists())
            self.assertIn("Confirm", error.call_args.args[2])
            w.confirmed.setChecked(True)
            w.number.setText("not a number")
            w.create_button.click()
            self.assertFalse(self.output.exists())
            self.assertIn("digits only", error.call_args.args[2])
            w.number.setText("1001")
            w.create_button.click()
            self.assertFalse(self.output.exists())
            self.assertIn("different from both inputs", error.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
