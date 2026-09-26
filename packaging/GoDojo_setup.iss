; GoDojo 安装脚本 (Inno Setup 6)
; ------------------------------------------------------------------
; 设计要点
;   1. 不装到 C:\Program Files —— KataGo 会把 GPU 调优缓存写到自己的
;      安装目录(KataGoData\opencltuning\),Program Files 不可写会导致
;      每次启动重新调优(3-10 分钟)。所以默认装到非系统盘根目录,
;      用户在安装向导里还能自己改。
;   2. 不复制到 %LOCALAPPDATA%\ —— 用户明确要求"整个软件就在一个目录里,
;      卸载时删干净即可"。
;   3. 双引擎一起装:OpenCL(GPU) 优先,没有独显/驱动不支持时程序会自动
;      降级到 CPU 版(见 core.engine_candidates)。
;   4. 权重只装一份在 models\,两个引擎共用,省 200MB。
;   5. 默认目录是运行时算的(见 [Code] GetDefaultDir):
;      F 盘 -> D 盘 -> 系统盘,谁存在用谁 —— 这样同一份安装包在
;      "有 F 盘的本机"和"只有 C 盘的外人机器"上都能装。
; ------------------------------------------------------------------

#define APP_NAME        "GoDojo"
#define APP_VERSION     "2.1.0"
#define APP_PUBLISHER   "GoDojo"
#define APP_EXE         "GoDojo.exe"

; 载荷来源(打包时由 build_installer.py 设定)
#define PAYLOAD         "D:\GoDojoBuild\dist_payload_full"
#define APP_DIST        "D:\GoDojoBuild\dist2\GoDojo"

[Setup]
AppId={{8F3A5C21-4D7B-4E96-9A1F-6B2C8E4D7A53}
AppName={#APP_NAME}
AppVersion={#APP_VERSION}
AppVerName={#APP_NAME} {#APP_VERSION}
AppPublisher={#APP_PUBLISHER}
DefaultDirName={code:GetDefaultDir}
DefaultGroupName=GoDojo
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=D:\GoDojoBuild\installer_out
OutputBaseFilename=GoDojo_v{#APP_VERSION}_Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
; 需要管理员权限:要写 D:\ 并创建快捷方式
PrivilegesRequired=admin
UninstallDisplayName={#APP_NAME} 围棋道场
UninstallDisplayIcon={app}\{#APP_EXE}
; 不需要关闭应用
CloseApplications=no

[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"
Name: "quicklaunchicon"; Description: "创建开始菜单快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce
Name: "warmup"; Description: "立即预热引擎(为显卡做首次调优,约 5-10 分钟)"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
; ---------- 1) 应用程序本体(PyInstaller onedir 产物) ----------
Source: "{#APP_DIST}\{#APP_EXE}";      DestDir: "{app}"; Flags: ignoreversion
Source: "{#APP_DIST}\_internal\*";      DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; 前端另外放一份到 exe 同级:web_dir() 优先读这里,用户改界面不用重新打包
Source: "{#APP_DIST}\_internal\web\*";  DestDir: "{app}\web"; Flags: ignoreversion recursesubdirs createallsubdirs

; ---------- 2) 配置(相对路径,装到哪都能用) ----------
Source: "{#PAYLOAD}\config.json";       DestDir: "{app}"; Flags: ignoreversion
Source: "{#PAYLOAD}\gtp_web.cfg";       DestDir: "{app}"; Flags: ignoreversion
Source: "{#PAYLOAD}\使用说明.md";        DestDir: "{app}"; Flags: ignoreversion

; ---------- 3) 双引擎 ----------
Source: "{#PAYLOAD}\KataGo-opencl\katago.exe"; DestDir: "{app}\KataGo-opencl"; Flags: ignoreversion
Source: "{#PAYLOAD}\KataGo-opencl\*.dll";      DestDir: "{app}\KataGo-opencl"; Flags: ignoreversion
Source: "{#PAYLOAD}\KataGo-cpu\katago.exe";    DestDir: "{app}\KataGo-cpu"; Flags: ignoreversion
Source: "{#PAYLOAD}\KataGo-cpu\*.dll";         DestDir: "{app}\KataGo-cpu"; Flags: ignoreversion
; GPU 调优缓存:带一份开发机的(同款显卡的用户首次启动就不用等 5-10 分钟调优;
; 不同显卡因文件名不匹配会被忽略,KataGo 自己重新调优,不会出错)
Source: "{#PAYLOAD}\KataGo-opencl\KataGoData\opencltuning\*.txt"; DestDir: "{app}\KataGo-opencl\KataGoData\opencltuning"; Flags: ignoreversion skipifsourcedoesntexist

; ---------- 4) 共享权重(两个引擎合用一个文件) ----------
Source: "{#PAYLOAD}\models\*.bin.gz";   DestDir: "{app}\models"; Flags: ignoreversion

; ---------- 5) 空目录(对局存档 / 外接AI),内容可为空 ----------
Source: "{#PAYLOAD}\games\*";           DestDir: "{app}\games"; Flags: ignoreversion recursesubdirs skipifsourcedoesntexist
Source: "{#PAYLOAD}\外接AI\*";           DestDir: "{app}\外接AI"; Flags: ignoreversion recursesubdirs skipifsourcedoesntexist

[Dirs]
; 这几个目录运行时需要写入(棋谱、日志、GPU 调优缓存),确保装完就可写
Name: "{app}";                          Permissions: users-modify
Name: "{app}\games";                    Permissions: users-modify
Name: "{app}\外接AI";                    Permissions: users-modify
Name: "{app}\KataGo-opencl";            Permissions: users-modify
Name: "{app}\KataGo-cpu";               Permissions: users-modify

[Icons]
Name: "{autoprograms}\GoDojo 围棋道场";   Filename: "{app}\{#APP_EXE}"; WorkingDir: "{app}"; IconFilename: "{app}\{#APP_EXE}"; Comment: "GoDojo 围棋道场"
Name: "{autodesktop}\GoDojo 围棋道场";    Filename: "{app}\{#APP_EXE}"; WorkingDir: "{app}"; IconFilename: "{app}\{#APP_EXE}"; Tasks: desktopicon; Comment: "GoDojo 围棋道场"

[Run]
; 顺序很关键:先预热(把显卡调优做掉),再启动程序 —— 这样用户第一次
; 打开就是秒开,不用盯着"正在首次调优"等十分钟。
; 预热进程是 --windowed 的没有控制台输出,结果写在 {app}\warmup.result
Filename: "{app}\{#APP_EXE}"; Parameters: "--warmup"; Tasks: warmup; Description: "预热引擎(为显卡做首次调优,约 5-10 分钟,仅首次需要)"; Flags: runhidden waituntilterminated; StatusMsg: "正在为显卡做引擎调优(约 5-10 分钟,仅首次需要)…装完就能秒开"
Filename: "{app}\{#APP_EXE}"; Description: "立即启动 GoDojo"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 运行时产物:日志 + GPU 调优缓存(不删会留在盘上)
Type: files;          Name: "{app}\godojo_web.log"
Type: filesandordirs; Name: "{app}\KataGo-opencl\KataGoData"
Type: filesandordirs; Name: "{app}\KataGo-cpu\KataGoData"
; 用户棋谱保留(如果 games 里有 .sgf,卸载时提示目录仍存在)

[Code]
// 默认安装目录:优先 F 盘,其次 D 盘,最后系统盘。
// 为什么不直接写死:这份安装包要给别人的机器用,别人的 F 盘可能是空的
// 或者根本没 F 盘。装在"非系统盘根目录"比 Program Files 合适,因为
// KataGo 要往安装目录写调优缓存(Program Files 写不进去 -> 每次重调优)。
function GetDefaultDir(Param: String): String;
begin
  if DirExists('F:\') then
    Result := 'F:\GoDojo'
  else if DirExists('D:\') then
    Result := 'D:\GoDojo'
  else
    Result := ExpandConstant('{sd}\GoDojo');
end;
