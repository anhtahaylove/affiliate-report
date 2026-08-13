#ifndef MyAppVersion
  #define MyAppVersion "2.0.26"
#endif

[Setup]
AppId={{E729344A-643D-4B99-98B4-455B79060530}
AppName=Affiliate Report
AppVersion={#MyAppVersion}
AppPublisher=Affiliate Report
DefaultDirName={localappdata}\AffiliateReport
DefaultGroupName=Affiliate Report
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\artifacts\installer
OutputBaseFilename=AffiliateReportSetup-v{#MyAppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\AffiliateReport.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousTasks=yes

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài Desktop"; GroupDescription: "Biểu tượng bổ sung:"; Flags: checkedonce

; Dọn runtime cũ trước khi chép bản mới: sót một .dll/.pyd lệch phiên bản là app không mở nổi.
; Chỉ đụng _internal, không bao giờ chạm {app}\data.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\build\installer-app\AffiliateReport\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\data"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\Affiliate Report"; Filename: "{app}\AffiliateReport.exe"; WorkingDir: "{app}"; IconFilename: "{app}\AffiliateReport.exe"
Name: "{autodesktop}\Affiliate Report"; Filename: "{app}\AffiliateReport.exe"; WorkingDir: "{app}"; IconFilename: "{app}\AffiliateReport.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AffiliateReport.exe"; Description: "Khởi chạy Affiliate Report"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
