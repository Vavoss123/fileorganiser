@echo off
rem Start File Organiser without a console window.
pushd "%~dp0"
start "" pythonw app.py
popd
