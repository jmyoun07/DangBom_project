; ==========================================================
;  DB-care Inno Setup Installer Script
;  입력:  dist\DB-care\           (PyInstaller 출력 폴더)
;  출력:  dist\DB-care_Setup_v{Version}.exe
;
;  빌드 방법:
;    1) powershell .\build-exe.ps1      (PyInstaller 로 dist\DB-care 생성)
;    2) ISCC.exe installer\DB-care.iss   (Inno Setup Compiler)
;       또는 build-setup.ps1 한 방에 실행
; ==========================================================

#define MyAppName        "DB-care"
#define MyAppVersion     "2.1.4"
#define MyAppPublisher   "DB-care"
#define MyAppExeName     "DB-care.exe"
#define MyAppDescription "Diabetes Complication Predictor"

[Setup]
; NOTE: 고유 AppId — 업데이트 설치 시 같은 프로그램으로 인식되려면 변경 금지
AppId={{A7C1F8E2-5B3D-4E0A-9C8B-DB1CAREv1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppDescription}

; 기본 설치 경로: C:\Program Files\DB-care  (관리자) / %LOCALAPPDATA%\Programs\DB-care (일반 사용자)
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=no

; 권한 — 가능하면 관리자, 안 되면 사용자 폴더로 자동 fallback.
; 도메인 PC 에서 UAC 거부되거나 일반 사용자 계정에서 실행해도 설치되도록.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline

; 출력 파일
OutputDir=..\dist
OutputBaseFilename=DB-care_Setup_v{#MyAppVersion}
; 아이콘은 있을 때만 적용 (없으면 Inno Setup 기본 아이콘)
#if FileExists("db-care.ico")
SetupIconFile=db-care.ico
#endif

; 압축
Compression=lzma2/max
SolidCompression=yes

; 인터페이스
WizardStyle=modern
ShowLanguageDialog=no
AllowNoIcons=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

; 64비트 전용
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon";        Description: "바탕화면에 바로가기 생성";              GroupDescription: "추가 아이콘:"; Flags: unchecked
Name: "startmenuicon";      Description: "시작 메뉴에 바로가기 생성";             GroupDescription: "추가 아이콘:"
Name: "uninstallshortcut";  Description: "바탕화면에 '제거' 단축키도 함께 생성";  GroupDescription: "추가 아이콘:"; Flags: unchecked

[Files]
; PyInstaller 가 생성한 dist\DB-care\ 전체를 설치
Source: "..\dist\DB-care\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; VC++ 2015-2022 재배포 패키지 — 빌드 PC 에 받아둔 경우만 번들
; (sklearn/xgboost/numpy/scipy DLL 로드 실패 방지)
#if FileExists("vc_redist.x64.exe")
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: VCRedistNeedsInstall
#endif
; WebView2 Evergreen Bootstrapper — pywebview fallback 용
#if FileExists("MicrosoftEdgeWebview2Setup.exe")
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: WebView2NeedsInstall
#endif

[Icons]
; 시작 메뉴 — 본 프로그램
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
; 바탕화면 — 본 프로그램
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; 시작 메뉴 — 제거 프로그램 (그룹 폴더 안)
Name: "{group}\{#MyAppName} 제거"; Filename: "{uninstallexe}"
; 바탕화면 — 제거 프로그램 (선택)
Name: "{autodesktop}\{#MyAppName} 제거"; Filename: "{uninstallexe}"; Tasks: uninstallshortcut

[Run]
; VC++ 2015-2022 재배포 패키지 자동 설치 (필요 시) — 본 프로그램 실행 전에
#if FileExists("vc_redist.x64.exe")
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Microsoft Visual C++ 2015-2022 재배포 패키지 설치 중..."; Check: VCRedistNeedsInstall; Flags: waituntilterminated
#endif
; WebView2 자동 설치 (필요 시) — 클린 Windows 에서 Edge --app 모드 실패 대비
#if FileExists("MicrosoftEdgeWebview2Setup.exe")
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Microsoft Edge WebView2 런타임 설치 중..."; Check: WebView2NeedsInstall; Flags: waituntilterminated
#endif
; 설치 완료 후 프로그램 바로 실행 (선택)
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 지금 실행"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 프로그램 폴더 캐시만 정리. 환자 DB(%APPDATA%\DB-care) 는 [Code] 섹션에서 사용자 선택.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// VC++ 2015-2022 x64 재배포 패키지가 이미 깔려 있는지 검사.
// HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64 의 'Installed' 값이 1 이면 OK.
// 64비트 OS 에서 32비트 인스톨러가 돌면 WoW64 리다이렉트 때문에 RegQueryDWordValue 만으로는
// 못 찾을 수 있어서 HKLM64 도 같이 체크한다.
function VCRedistNeedsInstall: Boolean;
var
  Installed: Cardinal;
  KeyPath: String;
begin
  KeyPath := 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64';
  if RegQueryDWordValue(HKLM64, KeyPath, 'Installed', Installed) and (Installed = 1) then
    Result := False
  else if RegQueryDWordValue(HKLM, KeyPath, 'Installed', Installed) and (Installed = 1) then
    Result := False
  else
    Result := True;
end;

// Edge WebView2 Runtime 이 깔려 있는지 검사.
// 머신/유저 양쪽 레지스트리 모두 확인 (Evergreen 은 머신, Per-User Bootstrapper 는 유저).
// pywebview fallback / Edge --app 일부 시나리오에서 필요하므로 없으면 silent install.
function WebView2NeedsInstall: Boolean;
var
  Version: String;
  ClientId: String;
begin
  ClientId := '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  if RegQueryStringValue(HKLM64, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + ClientId, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0') then
    Result := False
  else if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + ClientId, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0') then
    Result := False
  else if RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + ClientId, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0') then
    Result := False
  else
    Result := True;
end;

// 제거 시 환자 DB(%APPDATA%\DB-care) 도 함께 삭제할지 사용자에게 묻는다.
// 기본은 "아니오" — 실수로 환자 데이터를 잃지 않도록 보수적으로.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataPath: String;
  Response: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AppDataPath := ExpandConstant('{userappdata}') + '\DB-care';
    if DirExists(AppDataPath) then
    begin
      Response := MsgBox(
        '환자 데이터베이스를 함께 삭제하시겠습니까?' + #13#10 + #13#10 +
        '경로: ' + AppDataPath + #13#10 + #13#10 +
        '[예]    환자 정보 / 검사 수치 / 수정 이력 모두 영구 삭제 (복구 불가)' + #13#10 +
        '[아니오] 데이터 보존 — 추후 재설치 시 자동 복원',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2
      );
      if Response = IDYES then
      begin
        DelTree(AppDataPath, True, True, True);
      end;
    end;
  end;
end;
