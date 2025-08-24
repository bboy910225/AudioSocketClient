# main.py
import sys, threading
from services.login import LoginClient
from util.AudioInput import OutputDeviceDetector, AudioUIManager
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QPlainTextEdit, QWidget, QVBoxLayout, QLineEdit, QLabel, QFormLayout, QFileDialog, QHBoxLayout, QComboBox
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import Signal, QObject, QTimer, QFile
import signal
from services.client import AudioSocketClient


class Bus(QObject):
    log = Signal(str)
BUS = Bus()


class Win(QMainWindow):
    def __init__(self):
        super().__init__()
        # Load UI from .ui file created by Qt Designer
        loader = QUiLoader()
        ui_file = QFile("view/main_window.ui")
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
            # NOTE: Skip transferring menuBar/statusBar to avoid ownership/deletion issues.
            # If you need menus/status later, define them in this subclass or keep them in the .ui and use loaded directly.
            # keep reference so GC won't delete during init
            self._loaded_ui = loaded
        else:
            # otherwise, assume it's a QWidget and set as central
            self.setCentralWidget(loaded)
            self._loaded_ui = loaded

        self.in_app_base = self.findChild(QLineEdit, "in_app_base")
        self.in_username = self.findChild(QLineEdit, "in_username")
        self.in_password = self.findChild(QLineEdit, "in_password")
        self.in_login = self.findChild(QPushButton, "btn_login")
        self.in_login.clicked.connect(self.login)
        
        self.ui_channel_map_manager = AudioUIManager(self)  # 傳入 parent 視窗
        
        self.channel_mape_group = self.findChild(QWidget, "group_output_mapping")
        self.in_channel_map = self.findChild(QVBoxLayout, "output_mapping_layout")
        self.in_reload =  self.findChild(QPushButton, "btn_reload_output_mapping")
        self.channel_mape_group.setVisible(False)
        self.in_reload.clicked.connect(lambda: self.ui_channel_map_manager.populate_output_devices(self.area,force_reload=True))

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
    def login(self):
        BUS.log.emit("登入中...")
        self.client = LoginClient(
            app_base=self.in_app_base.text(),
            username=self.in_username.text(),
            password=self.in_password.text(),
            ca_verify=self.in_cafile.text(),
            log_func=lambda msg: BUS.log.emit(msg)
        )
        self.token, self.area = self.client.get_token()

        self.ui_channel_map_manager.populate_output_devices(self.area)
        self.channel_mape_group.setVisible(True)

    def start(self):
        if self.worker and self.worker.is_alive():
            BUS.log.emit("已經正在連線")
            return
        if self.token is None or self.token == "":
            BUS.log.emit("尚未登入")
        app_base = self.in_app_base.text().strip()
        token = self.token
        cafile = self.in_cafile
        # create client and keep reference for stopping later
        cafile = self.in_cafile.text().strip() or None
        self.cli = AudioSocketClient(app_base, self.ui_channel_map_manager, self.area, token, log_func=lambda msg: BUS.log.emit(msg),cafile=cafile, )
        def _worker():
            try:
                self.cli.connect()
                self.cli.run_forever()
            except Exception as e:
                BUS.log.emit(f"連線失敗: {e}")
        self.worker = threading.Thread(target=_worker, daemon=True)
        self.worker.start()
        BUS.log.emit(f"廣播練線開始 → 目標：{app_base}")

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