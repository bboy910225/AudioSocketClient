[app]

# title of your application
title = AudioSocketClient

# project root directory. default = The parent directory of input_file
project_dir = .

# source file entry point path. default = main.py
input_file = main.py

# directory where the executable output is generated
exec_directory = deployment

# path to the project file relative to project_dir
project_file = 

# application icon
icon = icon.ico


extra_ignore_dirs = .venv
[python]
packages = [
    "PySide6",
    "python-socketio",
    "requests",
    "simpleaudio",
    "websocket-client"
]
# python path
python_path =

[qt]

# paths to required qml files. comma separated
# normally all the qml files required by the project are added automatically
qml_files = 

# excluded qml plugin binaries
excluded_qml_plugins = 

# qt modules used. comma separated
modules = Core,Gui,Widgets

# qt plugins used by the application. only relevant for desktop deployment
# for qt plugins used in android application see [android][plugins]
plugins = platforms,imageformats,iconengines

[nuitka]

mode = onefile
extra_args = --noinclude-dlls=*.cpp.o --noinclude-dlls=*.qsb --noinclude-dlls=*.webp

[pyinstaller]
onefile = false
noconfirm = true
windowed = true
hiddenimports = PySide6