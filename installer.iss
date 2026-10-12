; Inno Setup script for File Organiser. Built by build.bat after the exe.
; Installs per user (no admin prompt) into %LOCALAPPDATA%\Programs.

#define AppName "File Organiser"
#ifndef AppVersion
  #define AppVersion "1.2"
#endif
#define AppExe "FileOrganiser.exe"

[Setup]
AppId={{6F3C2B8E-4D1A-4E7B-9C55-2A7E0F1B9D42}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Victor Stokoe
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=FileOrganiserSetup
SetupIconFile=build\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; The app adds this itself if you choose a sign-in option; remove it on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "FileOrganiser"; ValueType: none; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the tray watcher, if running, so its exe can be removed.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "StopTray"

; Settings and undo journals in %LOCALAPPDATA%\FileOrganiser are kept on purpose.
