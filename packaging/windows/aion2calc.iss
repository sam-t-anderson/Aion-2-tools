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
; a log of every run, "Setup Log <date> #<n>.txt" in %TEMP%, for when an install goes wrong
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "npcap"; Description: "Download and install Npcap for Live Capture"; GroupDescription: "Live Meter:"

[InstallDelete]
; An update no longer deletes the installed _internal here: SetPreviousAside (below) moves it aside
; with aion2calc.exe just before the new files are copied, so an update that does not finish can put
; them back, and the new copy still never mixes old and new libraries.
; Replace shortcuts created by the older lowercase product name.
Type: files; Name: "{autoprograms}\aion2calc.lnk"
Type: files; Name: "{autodesktop}\aion2calc.lnk"

[Files]
Source: "..\..\dist\aion2calc\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; BeforeInstall: SetPreviousAside

[UninstallDelete]
; the copy an update set aside, if the update was cut off before it could delete it
Type: filesandordirs; Name: "{app}\_previous"

[Icons]
Name: "{autoprograms}\Aion 2 Calc"; Filename: "{app}\aion2calc.exe"
Name: "{autodesktop}\Aion 2 Calc"; Filename: "{app}\aion2calc.exe"; Tasks: desktopicon

[Run]
; Npcap is separately licensed and is fetched only after the user explicitly opts in. The app resolves
; the current official installer at npcap.com, then opens Npcap's own interactive installer.
Filename: "{app}\aion2calc.exe"; Parameters: "--install-npcap"; Description: "Download and install Npcap now"; Tasks: npcap; Check: NeedsNpcap; Flags: postinstall waituntilterminated
; runs after a normal install (the checkbox) and after a silent auto-update, so the app relaunches;
; a scripted install that should not start it (the CI install test) passes /NOLAUNCH
Filename: "{app}\aion2calc.exe"; Description: "Start Aion 2 Calc now"; Flags: nowait postinstall; Check: Launch

[Code]
var
  AppDir: String;              { the install folder, set when the first file is about to be copied }
  PreviousSetAside: Boolean;   { the copy that was installed waits in _previous }
  NewCopyInstalled: Boolean;   { every file of the new copy is in place }

function NeedsNpcap: Boolean;
begin
  Result := not RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\npcap');
end;

function Launch: Boolean;
var
  I: Integer;
begin
  Result := True;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/NOLAUNCH') = 0 then
      Result := False;
end;

{ An update sets the installed copy aside, aion2calc.exe (which carries the app's code) with
  _internal (its Python runtime and libraries), and deletes it only once the new copy is in place.
  Setup's rollback removes what a cancelled or failed install had copied but cannot bring back what
  it had deleted, so deleting _internal first left an app that could not start ("Failed to load
  Python DLL ... python312.dll") whenever an update did not finish. }

function InApp(const Name: String): String;
begin
  Result := AddBackslash(AppDir) + Name;
end;

function InPrevious(const Name: String): String;
begin
  Result := AddBackslash(AppDir) + '_previous\' + Name;
end;

procedure DeletePrevious;
var
  Tries: Integer;
begin
  if AppDir = '' then
    Exit;                  { only ever inside the install folder }
  Tries := 0;
  while DirExists(InApp('_previous')) and (Tries < 10) do begin
    if Tries > 0 then
      Sleep(500);          { a file an antivirus is still reading }
    Tries := Tries + 1;
    DelTree(InApp('_previous'), True, True, True);
  end;
end;

function MoveAside(const Name: String): Boolean;
begin
  Result := True;
  if FileOrDirExists(InApp(Name)) then
    Result := RenameFile(InApp(Name), InPrevious(Name));
end;

procedure SetPreviousAside;
var
  Tries: Integer;
begin
  if AppDir <> '' then
    Exit;                  { BeforeInstall runs for every file: only the first one sets the copy aside }
  AppDir := RemoveBackslashUnlessRoot(ExpandConstant('{app}'));
  DeletePrevious;          { left by an update cut off (the computer turned off) before it could delete it }
  if not FileOrDirExists(InApp('_internal')) and not FileOrDirExists(InApp('aion2calc.exe')) then
    Exit;                  { a first install }
  { Setup has just closed the app: give it a few seconds to let go of its files }
  Tries := 0;
  while not PreviousSetAside and (Tries < 40) do begin
    if Tries > 0 then
      Sleep(250);
    Tries := Tries + 1;
    if DirExists(InApp('_previous')) or CreateDir(InApp('_previous')) then
      if MoveAside('_internal') then begin
        if MoveAside('aion2calc.exe') then
          PreviousSetAside := True
        else
          RenameFile(InPrevious('_internal'), InApp('_internal'));   { both or neither }
      end;
  end;
  if PreviousSetAside then
    Log('Set the installed copy aside in ' + InApp('_previous'))
  else begin
    { still in use: replace it in place, without leaving old libraries among the new ones }
    Log('Could not set the installed copy aside; replacing it in place.');
    PreviousSetAside := FileOrDirExists(InPrevious('_internal')) or FileOrDirExists(InPrevious('aion2calc.exe'));
    if not PreviousSetAside then
      RemoveDir(InApp('_previous'));
    DelTree(InApp('_internal'), True, True, True);
  end;
end;

procedure PutBack(const Name: String);
var
  Tries: Integer;
begin
  Tries := 0;
  while FileOrDirExists(InPrevious(Name)) and (Tries < 20) do begin
    if Tries > 0 then
      Sleep(250);
    Tries := Tries + 1;
    { what the unfinished update left in its place goes first }
    if DirExists(InApp(Name)) then
      DelTree(InApp(Name), True, True, True)
    else if FileExists(InApp(Name)) then
      DeleteFile(InApp(Name));
    RenameFile(InPrevious(Name), InApp(Name));
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    NewCopyInstalled := True;
    if PreviousSetAside then
      DeletePrevious;
  end;
end;

procedure DeinitializeSetup;
begin
  { cancelled, or failed and rolled back, after the installed copy was set aside }
  if PreviousSetAside and not NewCopyInstalled then begin
    Log('The update did not finish: putting the installed copy back.');
    PutBack('_internal');
    PutBack('aion2calc.exe');
    if not RemoveDir(InApp('_previous')) then begin
      Log('Could not put the installed copy back from ' + InApp('_previous'));
      SuppressibleMsgBox('Setup could not put back the copy of Aion 2 Calc that was installed. ' +
        'Run Setup again to install it; your data is kept.', mbError, MB_OK, IDOK);
    end;
  end;
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
