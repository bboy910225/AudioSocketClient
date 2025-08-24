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
                    output_devices.append({
                        'name': dev['name'],
                        'id': i
                    })
        except Exception as e:
            print(f"Error listing output devices: {e}")
        return output_devices

class AudioUIManager:
    def __init__(self, parent):
        self.parent = parent

    def populate_output_devices(self, areaList,force_reload=False):
        if force_reload:
            self.refresh_devices()
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
            label = QLabel(device["name"])
            label.setProperty("device_id", device["id"])
            combo = QComboBox()
            combo.addItem("不綁定", "")
            for area in areaList:
                combo.addItem(area["name"], f"private-audio.{area['code']}")
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
    def refresh_devices(self):
        try:
            sd._terminate()
            sd._initialize()
        except Exception as e:
            print(f"Failed to reinitialize PortAudio: {e}")
    def get_channel_map(self):
        channel_map = {}
        output_mapping_layout = self.parent.findChild(QVBoxLayout, "output_mapping_layout")
        if output_mapping_layout is None:
            return channel_map

        for i in range(output_mapping_layout.count()):
            item = output_mapping_layout.itemAt(i)
            if isinstance(item, QHBoxLayout):
                label = item.itemAt(0).widget()
                combo = item.itemAt(1).widget()
            elif item.layout():  # if it's a layout item
                row_layout = item.layout()
                label = row_layout.itemAt(0).widget()
                combo = row_layout.itemAt(1).widget()
            else:
                continue

            if label and combo:
                device_name = label.text().strip()
                device_id = label.property("device_id")
                selected_channel = combo.currentData()
                channel_map[device_id] = selected_channel

        return channel_map

if __name__ == "__main__":
    detector = OutputDeviceDetector()
    print(detector.get_output_devices())