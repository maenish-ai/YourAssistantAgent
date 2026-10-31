#define MyAppName "Your Assistant Agent"
#define MyAppVersion "5.2.0"
#define MyAppPublisher "Your Assistant Agent"
#define MyAppExeName "YourAssistantAgent.exe"
#define MyAppURL "https://github.com/maenish-ai/YourAssistantAgent"

[Setup]
AppId={{C82F4E4A-719F-45A5-8CF9-8457B108A140}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\Your Assistant Agent
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\output
OutputBaseFilename=YourAssistantAgent-Windows-Setup-v5.2.0
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
WizardImageFile=..\assets\installer_wizard.bmp
WizardSmallImageFile=..\assets\installer_small.bmp
SetupIconFile=..\assets\icon.ico
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
CloseApplications=no
RestartApplications=no
VersionInfoVersion=5.2.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Windows Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[CustomMessages]
english.CloseForUpdatePrompt=Setup will close the current Your Assistant Agent instance before updating.%n%nContinue?
english.CloseForUpdateCancelled=The update was cancelled.
arabic.CloseForUpdatePrompt=سيقوم برنامج التثبيت بإغلاق النسخة الحالية من Your Assistant Agent قبل التحديث.%n%nهل تريد المتابعة؟
arabic.CloseForUpdateCancelled=تم إلغاء التحديث.

[Files]
Source: "..\dist\YourAssistantAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent unchecked

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  Answer: Integer;
begin
  Result := '';
  NeedsRestart := False;

  if not WizardSilent then
  begin
    Answer := MsgBox(CustomMessage('CloseForUpdatePrompt'), mbConfirmation, MB_YESNO);
    if Answer <> IDYES then
    begin
      Result := CustomMessage('CloseForUpdateCancelled');
      Exit;
    end;
  end;

  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM {#MyAppExeName}',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Sleep(800);
end;
