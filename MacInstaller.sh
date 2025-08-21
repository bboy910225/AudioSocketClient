#!/bin/bash
set -e

pyinstaller --name "AudioSocketClient" \
  --windowed \
  --noconfirm \
  --collect-submodules PySide6 \
  --add-data "app.crt:." \
  main.py

mkdir -p build_dmg
cp -R dist/AudioSocketClient.app build_dmg/
ln -s /Applications build_dmg/Applications

# 2) 產生壓縮 DMG
hdiutil create -volname "AudioSocketClient" \
  -srcfolder build_dmg \
  -ov -format UDZO "AudioSocketClient.dmg"

# 做完可以刪暫存
rm -rf build_dmg
echo "DMG build complete: AudioSocketClient.dmg"