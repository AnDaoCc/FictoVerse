; FictoVerse (虚构宇宙) 安装脚本
; 使用 Inno Setup 6 编译

#define MyAppName "FictoVerse"
#define MyAppNameCN "虚构宇宙"
#define MyAppVersion "2026-V2"
#define MyAppPublisher "AnDaoCc"
#define MyAppURL "https://github.com/AnDaoCc/FictoVerse"
#define MyAppExeName "FictoVerse启动器.exe"

[Setup]
AppId={{FictoVerse-2026-V2-AnDaoCc}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion} ({#MyAppNameCN})
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=installer-stage\app\LICENSE
OutputDir=..\..\
OutputBaseFilename=FictoVerse_Setup_v2026-V2
SetupIconFile=installer-stage\app\launcher-icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
Source: "installer-stage\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\launcher-icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\launcher-icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch FictoVerse"; Flags: nowait postinstall skipifsilent shellexec

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigPath: String;
  ConfigContent: String;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigPath := ExpandConstant('{userappdata}\FictoVerse\launcher-config.json');
    ConfigContent := '{' + #13#10 +
                     '  "project_root": "' + ExpandConstant('{app}') + '"' + #13#10 +
                     '}';
    ForceDirectories(ExpandConstant('{userappdata}\FictoVerse'));
    SaveStringToFile(ConfigPath, ConfigContent, False);
  end;
end;
