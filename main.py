# main.py
import sys, threading
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QPlainTextEdit, QWidget, QVBoxLayout, QLineEdit, QLabel, QFormLayout, QFileDialog, QHBoxLayout
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import Signal, QObject, QTimer, QFile
import signal
from client import AudioSocketClient


class Bus(QObject):
    log = Signal(str)
BUS = Bus()


class Win(QMainWindow):
    def __init__(self):
        super().__init__()
        # Load UI from .ui file created by Qt Designer
        loader = QUiLoader()
        ui_file = QFile("main_window.ui")
        if not ui_file.open(QFile.ReadOnly):
            raise RuntimeError("Cannot open main_window.ui")
        # Load WITHOUT parent; we'll transfer parts safely below
        loaded = loader.load(ui_file)
        ui_file.close()
        if loaded is None:
            raise RuntimeError("Failed to load main_window.ui")

        # If the .ui root is a QMainWindow, transfer its parts into this subclass
        if isinstance(loaded, QMainWindow):
            # title
            self.setWindowTitle(loaded.windowTitle())
            # safely detach central widget from loaded (prevents deletion)
            cw = loaded.takeCentralWidget()
            if cw is not None:
                self.setCentralWidget(cw)
            # menubar / statusbar: detach first, then attach to self
            mb = loaded.menuBar()
            if mb is not None:
                loaded.setMenuBar(None)
                self.setMenuBar(mb)
            sb = loaded.statusBar()
            if sb is not None:
                loaded.setStatusBar(None)
                self.setStatusBar(sb)
            # keep reference so GC won't delete during init
            self._loaded_ui = loaded
        else:
            # otherwise, assume it's a QWidget and set as central
            self.setCentralWidget(loaded)
            self._loaded_ui = loaded

        # Bind widgets by objectName from the .ui
        self.in_app_base = self.findChild(QLineEdit, "in_app_base")
        self.in_username = self.findChild(QLineEdit, "in_username")
        self.in_password = self.findChild(QLineEdit, "in_password")
        self.in_group = self.findChild(QLineEdit, "in_group")
        self.in_cafile = self.findChild(QLineEdit, "in_cafile")
        self.log = self.findChild(QPlainTextEdit, "log")
        self.btn = self.findChild(QPushButton, "btn_start")
        self.btn_stop = self.findChild(QPushButton, "btn_stop")
        btn_browse = self.findChild(QPushButton, "btn_browse")
        if btn_browse is not None:
            btn_browse.clicked.connect(self._choose_cafile)

        # Wire signals
        if self.btn is not None:
            self.btn.clicked.connect(self.start)
        if self.btn_stop is not None:
            self.btn_stop.clicked.connect(self.stop)
        if self.log is not None:
            BUS.log.connect(lambda s: self.log.appendPlainText(s))

        # Runtime state
        self.worker = None
        self.cli = None

    def _choose_cafile(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Select Certificate", "", "Certificate Files (*.crt *.pem);;All Files (*)")
        if fn and self.in_cafile is not None:
            self.in_cafile.setText(fn)

    def start(self):
        if self.worker and self.worker.is_alive():
            BUS.log.emit("Already running")
            return
        app_base = self.in_app_base.text().strip()
        username = self.in_username.text().strip()
        password = self.in_password.text().strip()
        channel = self.in_group.text().strip()
        if not app_base or not channel or not username or not password:
            BUS.log.emit("Please fill app_base / username / password / group")
            return
        # create client and keep reference for stopping later
        cafile = self.in_cafile.text().strip() or None
        self.cli = AudioSocketClient(app_base, channel, username, password, cafile=cafile)
        def _worker():
            try:
                self.cli.connect()
                self.cli.run_forever()
            except Exception as e:
                BUS.log.emit(f"Worker error: {e}")
        self.worker = threading.Thread(target=_worker, daemon=True)
        self.worker.start()
        BUS.log.emit(f"Worker started → {app_base} / {channel}")

    def stop(self):
        if not self.worker:
            BUS.log.emit("Not running")
            return
        BUS.log.emit("Stopping...")
        try:
            if self.cli is not None:
                # Prefer class-provided disconnect if available
                if hasattr(self.cli, 'disconnect'):
                    self.cli.disconnect()
                elif hasattr(self.cli, 'sio'):
                    try:
                        self.cli.sio.disconnect()
                    except Exception:
                        pass
        except Exception as e:
            BUS.log.emit(f"Stop error: {e}")
        # give the thread a moment to exit
        self.worker.join(timeout=3)
        self.worker = None
        self.cli = None
        BUS.log.emit("Stopped")

    def closeEvent(self, event):
        try:
            self.stop()
        finally:
            super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Allow Ctrl+C to work in terminal with Qt
    signal.signal(signal.SIGINT, lambda *args: QApplication.quit())
    tick = QTimer()
    tick.start(200)
    tick.timeout.connect(lambda: None)
    w = Win(); w.resize(800, 500); w.show()
    sys.exit(app.exec())