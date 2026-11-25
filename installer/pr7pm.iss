; Paragon PR7-PM installer (Inno Setup 6): a password manager, the way KeePassXC keeps passwords.
;   iscc /DAppVersion=0.1.0 installer\pr7pm.iss      (after pyinstaller pr7pm.spec has made dist\PR7-PM)
;
; Per-user (no admin rights) into %LOCALAPPDATA%\Programs\PR7-PM, with a Start menu entry. Ticked by default, .kdbx
; files open with PR7-PM (written by PR7-PM itself: --register / --unregister, HKCU only, so installer and app agree).
; Uninstalling never touches your databases: they're your files, wherever you keep them.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId is permanent: it's how a new version finds and upgrades the installed one. Never change it.
AppId={{18BE3275-9FB9-46DF-9C29-060A544E4632}
AppName=Paragon PR7-PM
AppVersion={#AppVersion}
AppVerName=Paragon PR7-PM {#AppVersion}
AppPublisher=Paragon
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\PR7-PM
DefaultGroupName=Paragon PR7-PM
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=PR7-PM-Setup-{#AppVersion}
SetupIconFile=..\pr7pm\icons\app.ico
UninstallDisplayIcon={app}\PR7-PM.exe
UninstallDisplayName=Paragon PR7-PM
WizardStyle=modern
WizardImageFile=wizard-large-1x.bmp,wizard-large-2x.bmp
WizardSmallImageFile=wizard-small-1x.bmp,wizard-small-2x.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "kdbx"; Description: "Open .kdbx password databases with PR7-PM"; GroupDescription: "Windows:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PR7-PM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Paragon PR7-PM"; Filename: "{app}\PR7-PM.exe"; Comment: "Password manager"
Name: "{autodesktop}\Paragon PR7-PM"; Filename: "{app}\PR7-PM.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PR7-PM.exe"; Parameters: "--register"; Flags: runhidden waituntilterminated; Tasks: kdbx
Filename: "{app}\PR7-PM.exe"; Description: "{cm:LaunchProgram,Paragon PR7-PM}"; Flags: nowait postinstall skipifsilent
; Updates (Check for updates runs this installer with /SILENT /relaunch=1): start PR7-PM again when done.
Filename: "{app}\PR7-PM.exe"; Flags: nowait runasoriginaluser; Check: Relaunch

[UninstallRun]
Filename: "{app}\PR7-PM.exe"; Parameters: "--unregister"; Flags: runhidden waituntilterminated; RunOnceId: "Unregister"

[Code]
// True only when the updater asked for it (/relaunch=1): normal and CI installs behave as before.
function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;
