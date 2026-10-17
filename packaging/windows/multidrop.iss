; MultiDrop-Setup.exe: per-user install, no admin rights (Inno Setup 6).
;   iscc /DAppVersion=0.2.0 packaging\windows\multidrop.iss   (after building dist\MultiDrop.exe)
; The "Send to" shortcut and the Run value have the same names as in
; src/multidrop/winshell.py, so the tray menu and the installer switch the same entries.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={{10B10BCF-89B1-4852-A0E7-0464EA70C45A}
AppName=MultiDrop
AppVersion={#AppVersion}
AppPublisher=MultiDrop
AppPublisherURL=https://github.com/digitaldanis/multidrop
DefaultDirName={localappdata}\Programs\MultiDrop
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE
SetupIconFile=..\..\data\icons\multidrop.ico
UninstallDisplayIcon={app}\MultiDrop.exe
OutputDir=..\..\dist
OutputBaseFilename=MultiDrop-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The tray app has no window: close it for updates and uninstalling.
CloseApplications=force
RestartApplications=no

[Tasks]
Name: sendto; Description: "Show MultiDrop in Explorer's ""Send to"" menu"
Name: autostart; Description: "Start MultiDrop with Windows"
Name: desktopicon; Description: "Desktop shortcut"; Flags: unchecked

[Files]
Source: "..\..\dist\MultiDrop.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\MultiDrop"; Filename: "{app}\MultiDrop.exe"
Name: "{usersendto}\MultiDrop"; Filename: "{app}\MultiDrop.exe"; Tasks: sendto
Name: "{userdesktop}\MultiDrop"; Filename: "{app}\MultiDrop.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "MultiDrop"; \
  ValueData: """{app}\MultiDrop.exe"" --no-browser"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\MultiDrop.exe"; Description: "Start MultiDrop"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Also switched on later from the tray menu.
Type: files; Name: "{usersendto}\MultiDrop.lnk"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { The tray menu may have added it without the installer task. }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, '{#RunKey}', 'MultiDrop');
end;
