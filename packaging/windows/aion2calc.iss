; Inno Setup script for the aion2calc Windows installer.
; Built by the GitHub workflow:  iscc /DAppVersion=0.2.0 packaging\windows\aion2calc.iss
; Installs per user (no administrator rights) into %LOCALAPPDATA%\Programs\aion2calc.
; Your data (%LOCALAPPDATA%\aion2calc) stays when you uninstall or update.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E7A3F2B-5C1D-4E8A-9B0F-A2C4E6D8F012}
AppName=aion2calc
AppVersion={#AppVersion}
AppPublisher=aion2calc
DefaultDirName={localappdata}\Programs\aion2calc
DefaultGroupName=aion2calc
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=aion2calc-setup-{#AppVersion}
SetupIconFile=..\aion2calc.ico
UninstallDisplayIcon={app}\aion2calc.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[InstallDelete]
; an update replaces the bundled libraries instead of mixing old and new ones
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\..\dist\aion2calc\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\aion2calc"; Filename: "{app}\aion2calc.exe"
Name: "{autodesktop}\aion2calc"; Filename: "{app}\aion2calc.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\aion2calc.exe"; Description: "Start aion2calc now"; Flags: nowait postinstall skipifsilent
