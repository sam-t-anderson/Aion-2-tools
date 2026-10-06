; Inno Setup script for the aion2calc Windows installer.
; Built by the GitHub workflow:  iscc /DAppVersion=0.2.0 packaging\windows\aion2calc.iss
; Installs per user (no administrator rights) into %LOCALAPPDATA%\Programs\aion2calc.
; Your data (%LOCALAPPDATA%\aion2calc) stays when you uninstall or update.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E7A3F2B-5C1D-4E8A-9B0F-A2C4E6D8F012}
AppName=Aion 2 Calc
AppVersion={#AppVersion}
AppPublisher=Aion 2 Calc
AppPublisherURL=https://github.com/sam-t-anderson/Aion-2-tools
AppSupportURL=https://github.com/sam-t-anderson/Aion-2-tools/issues
AppUpdatesURL=https://github.com/sam-t-anderson/Aion-2-tools/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Aion 2 Calc
VersionInfoProductVersion={#AppVersion}
VersionInfoDescription=Aion 2 Calc installer
VersionInfoCopyright=GPL-3.0
DefaultDirName={localappdata}\Programs\aion2calc
DefaultGroupName=Aion 2 Calc
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
Name: "npcap"; Description: "Download and install Npcap for Live Capture"; GroupDescription: "Live Meter:"

[InstallDelete]
; an update replaces the bundled libraries instead of mixing old and new ones
Type: filesandordirs; Name: "{app}\_internal"
; Replace shortcuts created by the older lowercase product name.
Type: files; Name: "{autoprograms}\aion2calc.lnk"
Type: files; Name: "{autodesktop}\aion2calc.lnk"

[Files]
Source: "..\..\dist\aion2calc\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Aion 2 Calc"; Filename: "{app}\aion2calc.exe"
Name: "{autodesktop}\Aion 2 Calc"; Filename: "{app}\aion2calc.exe"; Tasks: desktopicon

[Run]
; Npcap is separately licensed and is fetched only after the user explicitly opts in. The app resolves
; the current official installer at npcap.com, then opens Npcap's own interactive installer.
Filename: "{app}\aion2calc.exe"; Parameters: "--install-npcap"; Description: "Download and install Npcap now"; Tasks: npcap; Check: NeedsNpcap; Flags: postinstall waituntilterminated
; runs after a normal install (the checkbox) and after a silent auto-update, so the app relaunches
Filename: "{app}\aion2calc.exe"; Description: "Start Aion 2 Calc now"; Flags: nowait postinstall

[Code]
function NeedsNpcap: Boolean;
begin
  Result := not RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\npcap');
end;

procedure CurPageChanged(CurPageID: Integer);
var
  I: Integer;
begin
  if CurPageID = wpSelectTasks then
    for I := 0 to WizardForm.TasksList.Items.Count - 1 do
      if Pos('Npcap', WizardForm.TasksList.ItemCaption[I]) > 0 then begin
        WizardForm.TasksList.ItemEnabled[I] := NeedsNpcap;
        if not NeedsNpcap then begin
          WizardForm.TasksList.Checked[I] := False;
          WizardForm.TasksList.ItemSubItem[I] := 'Already installed';
        end;
      end;
end;
