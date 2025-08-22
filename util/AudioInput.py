import platform
import sounddevice as sd
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QComboBox

class OutputDeviceDetector:
    def __init__(self):
        pass

    def get_output_devices(self):
        output_devices = []
        try:
            all_devices = sd.query_devices()
            for i, dev in enumerate(all_devices):
                if dev['max_output_channels'] > 0:
                    output_devices.append(dev['name'])
        except Exception as e:
            print(f"Error listing output devices: {e}")
        return output_devices

class AudioUIManager:
    def __init__(self, parent):
        self.parent = parent

    def populate_output_devices(self):
        detector = OutputDeviceDetector()
        output_devices = detector.get_output_devices()
        output_mapping_layout = self.parent.findChild(QVBoxLayout, "output_mapping_layout")
        
        # 清空舊資料（重要！）
        while output_mapping_layout.count():
            child = output_mapping_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._delete_layout(child.layout())

        for device in output_devices:
            layout = QHBoxLayout()
            label = QLabel(device)
            combo = QComboBox()
            combo.addItems([
                "private-audio.Lobby",
                "private-audio.Room1",
                "private-audio.Room2",
                "private-audio.Game",
                "private-audio.Dev"
            ])
            layout.addWidget(label)
            layout.addWidget(combo)
            output_mapping_layout.addLayout(layout)

    def _delete_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._delete_layout(item.layout())

if __name__ == "__main__":
    detector = OutputDeviceDetector()
    print(detector.get_output_devices())