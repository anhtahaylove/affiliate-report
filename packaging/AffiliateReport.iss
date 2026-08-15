#ifndef MyAppVersion
  #define MyAppVersion "2.1.4"
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
; Từ v2.0.29 updater chấp nhận cả tên cũ lẫn tên mới. Giữ tên EXE nội bộ để bootstrap có thể
; khởi động lại ứng dụng, nhưng mọi tên hiển thị cho người dùng chỉ còn Affiliate Report.
OutputBaseFilename=AffiliateReportSetup-v{#MyAppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\TikTokAffiliateReport.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
UsePreviousGroup=no

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài Desktop"; GroupDescription: "Biểu tượng bổ sung:"; Flags: checkedonce

; Dọn runtime cũ trước khi chép bản mới: sót một .dll/.pyd lệch phiên bản là app không mở nổi.
; Chỉ đụng _internal, không bao giờ chạm {app}\data.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
; Dọn dấu vết shortcut từ các bản TikTok Affiliate Report cũ. Dữ liệu ứng dụng không nằm ở đây.
Type: filesandordirs; Name: "{userprograms}\TikTok Affiliate Report"
Type: files; Name: "{userprograms}\Affiliate Report\TikTok Affiliate Report.lnk"
Type: files; Name: "{userdesktop}\TikTok Affiliate Report.lnk"

[Files]
Source: "..\build\installer-app\TikTokAffiliateReport\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\data"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\Affiliate Report"; Filename: "{app}\TikTokAffiliateReport.exe"; WorkingDir: "{app}"; IconFilename: "{app}\TikTokAffiliateReport.exe"
Name: "{autodesktop}\Affiliate Report"; Filename: "{app}\TikTokAffiliateReport.exe"; WorkingDir: "{app}"; IconFilename: "{app}\TikTokAffiliateReport.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TikTokAffiliateReport.exe"; Description: "Khởi chạy Affiliate Report"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
