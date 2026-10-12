@echo off
rem Build dist\FileOrganiser.exe, and the installer too if Inno Setup is installed.
setlocal
pushd "%~dp0"

python -m pip install --quiet pyinstaller pystray pillow || goto :fail
if not exist build mkdir build
python -c "from organiser.icon import save_ico; save_ico(r'build\icon.ico')" || goto :fail

rem pystray picks its Windows backend at runtime, so name it explicitly.
python -m PyInstaller --noconfirm --onefile --windowed --name FileOrganiser ^
    --icon build\icon.ico --hidden-import pystray._win32 app.py || goto :fail

set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
    if exist %%P set "ISCC=%%~P"
)
if defined ISCC (
    rem APP_VERSION, when set (the release workflow sets it from the tag), stamps the installer.
    if defined APP_VERSION (
        "%ISCC%" /Q "/DAppVersion=%APP_VERSION%" installer.iss || goto :fail
    ) else (
        "%ISCC%" /Q installer.iss || goto :fail
    )
    echo Installer: dist\FileOrganiserSetup.exe
) else (
    echo Inno Setup not found - skipped the installer. dist\FileOrganiser.exe is ready.
)
popd
exit /b 0

:fail
echo Build failed.
popd
exit /b 1
