#define MyAppName "Your Assistant Agent"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Your Assistant Agent"
#define MyAppExeName "YourAssistantAgent.exe"

[Setup]
AppId={{BCF9FD95-7625-49C5-9CD0-3461189D785D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Your Assistant Agent
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile=..\assets\installer_wizard.bmp
WizardSmallImageFile=..\assets\installer_small.bmp
SetupIconFile=..\assets\icon.ico
OutputDir=..\release
OutputBaseFilename=YourAssistantAgent-Setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

; We close the running app ourselves in PrepareToInstall.
; This prevents the old "applications are using files" screen.
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[CustomMessages]
english.CloseForUpdateTitle=Update Your Assistant Agent
english.CloseForUpdatePrompt=Setup will automatically close Your Assistant Agent and its dedicated browser processes so the update can continue.%n%nAny unrelated Chrome or other applications will not be intentionally closed.%n%nContinue?
english.CloseForUpdateCancelled=The update was cancelled. Close Setup when you are ready.
english.ClosingForUpdate=Closing the current version and its dedicated browser...
arabic.CloseForUpdateTitle=تحديث Your Assistant Agent
arabic.CloseForUpdatePrompt=سيقوم برنامج التثبيت الآن بإغلاق Your Assistant Agent ومتصفح البرنامج المخصص تلقائياً حتى يكتمل التحديث.%n%nلن يتم إغلاق متصفح Chrome أو البرامج الأخرى غير التابعة للبرنامج بشكل مقصود.%n%nهل تريد المتابعة؟
arabic.CloseForUpdateCancelled=تم إلغاء التحديث. يمكنك إغلاق برنامج التثبيت والمحاولة لاحقاً.
arabic.ClosingForUpdate=جارٍ إغلاق النسخة الحالية والمتصفح المخصص...

[Files]
Source: "..\dist\YourAssistantAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function CloseCurrentVersion: Boolean;
var
  ResultCode: Integer;
begin
  Result := True;

  WizardForm.StatusLabel.Caption := CustomMessage('ClosingForUpdate');
  WizardForm.Refresh;

  { Close only YourAssistantAgent.exe and its child process tree.
    /T includes Playwright/Node/dedicated Chromium children.
    /F ensures a stuck old version cannot block the update. }
  if not Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM {#MyAppExeName}',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    Log('Could not start taskkill. Setup will still continue.');
  end
  else
  begin
    Log(Format('taskkill finished with exit code %d', [ResultCode]));
  end;

  { Give Windows a short moment to release file handles. }
  Sleep(1200);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Answer: Integer;
begin
  Result := '';
  NeedsRestart := False;

  if not WizardSilent then
  begin
    Answer := MsgBox(
      CustomMessage('CloseForUpdatePrompt'),
      mbConfirmation,
      MB_YESNO
    );

    if Answer <> IDYES then
    begin
      Result := CustomMessage('CloseForUpdateCancelled');
      Exit;
    end;
  end;

  if not CloseCurrentVersion then
    Result := CustomMessage('CloseForUpdateCancelled');
end;
