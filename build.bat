@echo off
rem Build a standalone FileOrganiser.exe into dist\.
pushd "%~dp0"
python -m pip install --quiet pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name FileOrganiser app.py
popd
