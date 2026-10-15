#define MyAppName "Your Assistant Agent"
#define MyAppVersion "1.4.0"
#define MyAppExeName "YourAssistantAgent.exe"

[Setup]
AppId={{C82F4E4A-719F-45A5-8CF9-8457B108A140}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Your Assistant Agent
DefaultGroupName={#MyAppName}
OutputDir=..\output
OutputBaseFilename=YourAssistantAgent-Windows-Setup-v1.4.0
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequired=lowest

[Files]
Source: "..\dist\YourAssistantAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
