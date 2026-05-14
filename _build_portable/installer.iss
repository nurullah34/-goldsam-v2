; GOLDSAM V2 — Inno Setup installer script

#define MyAppName "GOLDSAM V2"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "GOLDSAM"
#define MyAppExeName "BASLAT.bat"

[Setup]
AppId={{C9F4C8E2-5A11-4B6F-9C7E-9D8F3A1B2C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; User-writable konum: %LOCALAPPDATA%\Programs\GOLDSAM V2
; Program Files'a kurulduğunda bot kendi dosyalarını update edemiyor,
; PID yazamıyor — bu nedenle user folder kullanıyoruz.
DefaultDirName={localappdata}\Programs\GOLDSAM V2
DefaultGroupName=GOLDSAM V2
DisableProgramGroupPage=auto
OutputDir=..
OutputBaseFilename=GOLDSAM_V2_KURULUM_v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\BASLAT.bat
LicenseFile=
ShowLanguageDialog=no
LanguageDetectionMethod=none

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Files]
; Tüm proje source (project root'tan)
Source: "..\main.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\version.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\core\*.py"; DestDir: "{app}\core"; Flags: ignoreversion
Source: "..\ui\*.py"; DestDir: "{app}\ui"; Flags: ignoreversion

; Embedded Python runtime + tüm bağımlılıklar
Source: "python_runtime\*"; DestDir: "{app}\python_runtime"; Flags: ignoreversion recursesubdirs createallsubdirs

; Launcher BAT'leri + VC++ Redistributable
Source: "BASLAT.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "TANI.bat"; DestDir: "{app}"; Flags: ignoreversion
; vc_redist KALICI tutuluyor — BASLAT.bat fallback'i için lazım
Source: "vc_redist.x64.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{sys}\imageres.dll"; IconIndex: 27
Name: "{group}\Tani (Sorun Tespit)"; Filename: "{app}\TANI.bat"; WorkingDir: "{app}"; IconFilename: "{sys}\imageres.dll"; IconIndex: 100
Name: "{group}\Kaldir"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{sys}\imageres.dll"; IconIndex: 27; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Masaustune kisayol olustur"; GroupDescription: "Ek kisayollar:"

[Run]
; Kurulum sonrasi VC++ Runtime kur (eksikse)
Filename: "{app}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Visual C++ Runtime kontrol ediliyor..."; Flags: runhidden
; Kurulum bitince botu otomatik baslat (opsiyonel)
Filename: "{app}\{#MyAppExeName}"; Description: "GOLDSAM V2'yi simdi baslat"; Flags: postinstall shellexec skipifsilent nowait

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python_runtime\__pycache__"
Type: filesandordirs; Name: "{app}\__pycache__"
