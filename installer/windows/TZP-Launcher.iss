#define AppName "TZP Launcher"
#ifndef MyAppVersion
  #define MyAppVersion "1.1.5"
#endif
#define AppExeName "TZP-Launcher.exe"

[Setup]
AppName={#AppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\TZP Launcher
DefaultGroupName=TZP Launcher
OutputBaseFilename=TZP-Launcher-Windows-Setup
OutputDir=.
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Files]
Source: "..\..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
