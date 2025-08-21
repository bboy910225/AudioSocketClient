# main.py
import sys, threading
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QPlainTextEdit, QWidget, QVBoxLayout, QLineEdit, QLabel, QFormLayout, QFileDialog, QHBoxLayout
from PySide6.QtCore import Signal, QObject, QTimer
import signal
from client import AudioSocketClient


class Bus(QObject):
    log = Signal(str)
BUS = Bus()


class Win(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Echo Listener · Socket Audio Client")
        # Inputs
        self.in_app_base = QLineEdit()
        self.in_app_base.setPlaceholderText("https://tta-ad")
        self.in_app_base.setText("https://tta-ad")

        self.in_username = QLineEdit()
        self.in_username.setPlaceholderText("username")
        self.in_username.setText("456456")

        self.in_password = QLineEdit()
        self.in_password.setPlaceholderText("password")
        self.in_password.setEchoMode(QLineEdit.Password)
        self.in_password.setText("456456")

        self.in_group = QLineEdit()
        self.in_group.setPlaceholderText("private-audio.Lobby")
        self.in_group.setText("private-audio.Lobby")

        self.in_cafile = QLineEdit()
        self.in_cafile.setPlaceholderText("Path to app.crt")
        btn_browse = QPushButton("Browse…")
        def choose_file():
            fn, _ = QFileDialog.getOpenFileName(self, "Select Certificate", "", "Certificate Files (*.crt *.pem);;All Files (*)")
            if fn:
                self.in_cafile.setText(fn)
        btn_browse.clicked.connect(choose_file)
        row = QHBoxLayout()
        row.addWidget(self.in_cafile)
        row.addWidget(btn_browse)

        form = QFormLayout()
        form.addRow(QLabel("App Base"), self.in_app_base)
        form.addRow(QLabel("Username"), self.in_username)
        form.addRow(QLabel("Password"), self.in_password)
        form.addRow(QLabel("Group / Channel"), self.in_group)
        form.addRow(QLabel("CA File"), row)

        self.log = QPlainTextEdit(readOnly=True)
        self.btn = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.stop)
        BUS.log.connect(lambda s: self.log.appendPlainText(s))
        lay = QVBoxLayout()
        lay.addLayout(form)
        lay.addWidget(self.log)
        lay.addWidget(self.btn)
        lay.addWidget(self.btn_stop)
        w = QWidget(); w.setLayout(lay); self.setCentralWidget(w)
        self.worker = None
        self.cli = None

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