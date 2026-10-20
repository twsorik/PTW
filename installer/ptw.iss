; Установщик PTW. Собирается скриптом build.ps1 (он передаёт /DMyAppVersion=...).
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "PTW"
#define MyAppExe "PTW.exe"
#define ProgId "PTW.Video"

[Setup]
AppId={{6B7F3E2A-9C41-4D8E-A5F2-3E1B7C9D0F42}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
VersionInfoVersion={#MyAppVersion}
; установка для текущего пользователя: без запроса прав администратора,
; поэтому и обновления ставятся молча
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist
OutputBaseFilename=PTW-Setup-{#MyAppVersion}
SetupIconFile=..\assets\ptw.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=force
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; убрать файлы прошлой версии, чтобы не копились
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\PTW\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; тип файла «Видео (PTW)»
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueData: "Видео (PTW)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExe},0"
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""
; само приложение (для «Открыть с помощью»)
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""
; регистрация в «Приложениях по умолчанию» Windows
Root: HKA; Subkey: "Software\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Видеоплеер с выбором аудиодорожек"
Root: HKA; Subkey: "Software\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\{#MyAppExe},0"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "Software\{#MyAppName}\Capabilities"; Flags: uninsdeletevalue
; форматы
#define Ext(str E) \
  "Root: HKA; Subkey: ""Software\Classes\" + E + "\OpenWithProgids""; ValueType: string; ValueName: """ + ProgId + """; ValueData: """"; Flags: uninsdeletevalue" + NewLine + \
  "Root: HKA; Subkey: ""Software\Classes\Applications\" + MyAppExe + "\SupportedTypes""; ValueType: string; ValueName: """ + E + """; ValueData: """"" + NewLine + \
  "Root: HKA; Subkey: ""Software\" + MyAppName + "\Capabilities\FileAssociations""; ValueType: string; ValueName: """ + E + """; ValueData: """ + ProgId + """" + NewLine
#emit Ext(".mp4")
#emit Ext(".mkv")
#emit Ext(".mov")
#emit Ext(".avi")
#emit Ext(".webm")
#emit Ext(".m4v")
#emit Ext(".ts")
#emit Ext(".flv")
#emit Ext(".wmv")
#emit Ext(".mpg")
#emit Ext(".mpeg")
#emit Ext(".3gp")

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
Filename: "ms-settings:defaultapps?registeredAppUser={#MyAppName}"; Description: "Сделать PTW плеером по умолчанию (откроются настройки Windows)"; Flags: shellexec nowait postinstall skipifsilent unchecked
; после тихого обновления из самого плеера — запустить его снова
Filename: "{app}\{#MyAppExe}"; Flags: nowait; Check: WizardSilent
