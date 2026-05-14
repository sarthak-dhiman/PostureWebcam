; posturecam_setup.iss
; =============================================================
; Inno Setup 6 script — PostureCam (Posture Webcam Analyzer)
;
; Build:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" posturecam_setup.iss
;
; Prerequisites:
;   • PyInstaller step already run: dist\PostureApp\ must exist
; =============================================================

#define AppName        "PostureCam"
#define AppExeName     "PostureCam.exe"
#define AppVersion     "1.0.0"
#define AppPublisher   "Posture Technologies Ltd"
#define AppURL         "https://postureos.onrender.com"
#define AppId          "{{A7B3C921-0F4E-4D2B-8E1A-62D5F93C7AB0}"
#define OutputFile     "PostureCamSetup"
; Path to the PyInstaller output folder (relative to this script)
#define DistDir        "dist\PostureCam"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/support
AppUpdatesURL={#AppURL}/updates

; Per-user install — no UAC prompt required
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Installation directory
DefaultDirName={autopf}\PostureCam
DefaultGroupName={#AppName}
DisableProgramGroupPage=no
AllowNoIcons=yes

; Output
OutputDir=dist
OutputBaseFilename={#OutputFile}
SetupIconFile=office.ico

; Compression
;
; Keep the PyInstaller onedir payload byte-for-byte in the installer.
; ONNX Runtime loads native DLLs/PYD files from _internal at process start,
; and the previous lzma2/ultra64 + solid compression build has produced
; installed copies that fail during ONNX Runtime import on target machines.
Compression=none
SolidCompression=no

; Appearance
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no

; Uninstaller
Uninstallable=yes
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

; Require Windows 10 or later
MinVersion=10.0

; Architecture — 64-bit only
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; =============================================================
; FILES
; =============================================================
[Files]
; Recursively include the entire PyInstaller output directory
Source: "{#DistDir}\*"; DestDir: "{app}"; \
  Excludes: "live_stats.json,live_frame.jpg,posture_tracker.log,onnx_import_error.txt,_internal\live_stats.json,_internal\live_frame.jpg,_internal\posture_tracker.log,_internal\onnx_import_error.txt"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; Licence text (optional — create a LICENSE.txt if desired)
; Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

; =============================================================
; SHORTCUTS
; =============================================================
[Icons]
; Start Menu
Name: "{group}\{#AppName}";          Filename: "{app}\{#AppExeName}"; \
      WorkingDir: "{app}"; IconFilename: "{app}\office.ico"; Comment: "Launch PostureCam"

Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; Desktop shortcut
Name: "{autodesktop}\{#AppName}";    Filename: "{app}\{#AppExeName}"; \
      WorkingDir: "{app}"; IconFilename: "{app}\office.ico"; \
      Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

; =============================================================
; REGISTRY
; =============================================================
[Registry]
; ── Auto-start on Windows login (launches minimized to tray) ──────────────
Root: HKCU; \
  Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; \
  ValueName: "PostureCam"; \
  ValueData: """{app}\{#AppExeName}"" --minimized"; \
  Flags: uninsdeletevalue

; App User Model ID — ensures Windows uses the app icon in notifications
; and the taskbar, not the generic Python icon.
Root: HKCU; \
  Subkey: "Software\Classes\AppUserModelId\PostureWebcamAnalyzer.App.1"; \
  ValueType: string; \
  ValueName: "DisplayName"; \
  ValueData: "{#AppName}"; \
  Flags: uninsdeletekey

; =============================================================
; RUN AFTER INSTALL
; =============================================================
[Run]
; Launch the app silently to the tray after installation finishes
Filename: "{app}\{#AppExeName}"; \
  Parameters: "--minimized"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent unchecked

; =============================================================
; KILL RUNNING INSTANCES BEFORE UNINSTALL / UPGRADE
; =============================================================
[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM PostureCam.exe";      RunOnceId: "KillMain";    Flags: runhidden waituntilterminated
Filename: "taskkill"; Parameters: "/F /IM tracker_daemon.exe";  RunOnceId: "KillDaemon";  Flags: runhidden waituntilterminated

[UninstallDelete]
; Remove user-written runtime files so the uninstall is completely clean
Type: files;     Name: "{app}\live_stats.json"
Type: files;     Name: "{app}\live_frame.jpg"
Type: filesandordirs; Name: "{app}\data\reports"
Type: filesandordirs; Name: "{app}\data\snapshots"
Type: filesandordirs; Name: "{app}\data\segregated"
Type: files;     Name: "{app}\data\auth_cache.json"
Type: files;     Name: "{app}\data\jwt_cache.json"
Type: files;     Name: "{app}\data\tracker_daemon.pid"
Type: dirifempty; Name: "{app}\data"
Type: dirifempty; Name: "{app}"

; =============================================================
; PASCAL SCRIPT — kill running instances before files are touched
; =============================================================
[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  // Kill any running instances before the installer touches the files.
  Exec('taskkill', '/F /IM PostureCam.exe',     '', SW_HIDE, ewWaitUntilTerminated, ResultCode);  // noqa
  Exec('taskkill', '/F /IM tracker_daemon.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);  // noqa
  Sleep(600);
  Result := True;
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill', '/F /IM PostureCam.exe',     '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec('taskkill', '/F /IM tracker_daemon.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(600);
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Remove the auto-start registry value (belt-and-suspenders; Flags already handles this)
    RegDeleteValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Run',
      'PostureCam');
  end;
end;
