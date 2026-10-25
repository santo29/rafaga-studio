; Instalador de Ráfaga Studio (Inno Setup 7): compílalo con  ISCC instalador\rafaga.iss  -> dist\RafagaStudio-Setup-<versión>.exe
;
; Instalador ligero: lleva la app (unos MB) y, al instalar, baja de sus fuentes oficiales:
; - Python (el paquete «python» de NuGet, de la Python Software Foundation: portátil, no se registra en Windows),
;   comprobando su huella SHA-256;
; - las librerías, con pip y las mismas versiones y huellas que requirements.lock (nada distinto de lo probado entra).
; Se instala solo para tu usuario (sin permisos de administrador), así la carpeta «datos» de la app se puede escribir.
; Python siempre con -s: nunca mezcla las librerías de la cuenta de Windows (%APPDATA%\Python) con las de la app.

#define Nombre "Ráfaga Studio"
#define Version "1.0.0"
#define Titular "Santo Montilla"
#define PythonVersion "3.14.9"
#define PythonSha256 "7cd9d07aec975212344dc6f7e45019378cf6775dd564181e269010a1eddaaec7"
; Lo que ocupa Python ya descomprimido (con extractarchive, Inno pide el tamaño descomprimido)
#define PythonTamano "41702504"

; Ráfaga Guardia: el manifiesto de integridad (la huella SHA-256 de cada archivo de código, ver instalador\integridad.py)
; se rehace en cada compilación con el Python del proyecto, así nunca se empaqueta uno viejo: uno viejo haría que la app
; instalada viera su propio código como cambiado y se bloqueara. Si falla, no se compila.
#if Exec(AddBackslash(SourcePath) + "..\.venv\Scripts\python.exe", "-s -E instalador\integridad.py", AddBackslash(SourcePath) + "..", 1, 0) != 0
  #error No se pudo generar dist\integridad.json: ejecuta .venv\Scripts\python.exe -s -E instalador\integridad.py y mira el error
#endif

[Setup]
AppId={{F4E4489A-13B7-423F-8FA7-A074C052C272}
AppName={#Nombre}
AppVersion={#Version}
AppVerName={#Nombre} {#Version}
AppPublisher={#Titular}
AppCopyright=© 2026 {#Titular}. Ráfaga Studio™
AppPublisherURL=https://github.com/santo29/rafaga-studio
VersionInfoVersion={#Version}
DefaultDirName={autopf}\{#Nombre}
; Siempre en %LOCALAPPDATA%\Programs (solo tu cuenta puede escribir ahí). En C:\Ráfaga Studio o en D:\…, cualquier
; otra cuenta del PC podría cambiar el código de la app y robar tus claves al abrirla. Ver PrepareToInstall.
DisableDirPage=yes
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\TERMINOS.md
SetupIconFile=..\assets\icono.ico
UninstallDisplayIcon={app}\assets\icono.ico
UninstallDisplayName={#Nombre}
WizardStyle=modern dynamic
OutputDir=..\dist
OutputBaseFilename=RafagaStudio-Setup-{#Version}
Compression=lzma2/max
SolidCompression=yes
ArchiveExtraction=full
CloseApplications=yes
; Las librerías que pip instala después (~2,2 GB) no están en [Files]: que el asistente pida ese espacio libre
ExtraDiskSpaceRequired=2500000000

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
es.Librerias=Instalando las librerías de IA (unos 1,5 GB; puede tardar de 10 a 30 minutos según tu internet)…
en.Librerias=Installing the AI libraries (about 1.5 GB; it can take 10 to 30 minutes depending on your internet)…
pt.Librerias=Instalando as bibliotecas de IA (cerca de 1,5 GB; pode levar de 10 a 30 minutos conforme sua internet)…
fr.Librerias=Installation des bibliothèques d'IA (environ 1,5 Go ; 10 à 30 minutes selon votre connexion)…
es.FalloLibrerias=No se pudieron instalar las librerías (¿sin internet?).%n%n%1%n%nPulsa «Reintentar» para probar otra vez, o «Cancelar» y vuelve a abrir este instalador cuando tengas internet: seguirá donde se quedó.
en.FalloLibrerias=The libraries could not be installed (no internet?).%n%n%1%n%nClick “Retry” to try again, or “Cancel” and run this installer again when you are online: it will continue where it stopped.
pt.FalloLibrerias=Não foi possível instalar as bibliotecas (sem internet?).%n%n%1%n%nClique em «Repetir» para tentar de novo, ou «Cancelar» e abra este instalador de novo quando tiver internet: ele continua de onde parou.
fr.FalloLibrerias=Les bibliothèques n'ont pas pu être installées (pas d'internet ?).%n%n%1%n%nCliquez sur « Réessayer » pour recommencer, ou « Annuler » et relancez ce programme d'installation une fois en ligne : il reprendra là où il s'est arrêté.
es.Incompleta=Ráfaga Studio quedó instalado, pero le faltan librerías. Vuelve a abrir este instalador con internet para terminar.
en.Incompleta=Ráfaga Studio is installed, but some libraries are missing. Run this installer again when you are online to finish.
pt.Incompleta=O Ráfaga Studio foi instalado, mas faltam bibliotecas. Abra este instalador de novo com internet para terminar.
fr.Incompleta=Ráfaga Studio est installé, mais il manque des bibliothèques. Relancez ce programme d'installation une fois en ligne pour terminer.
es.CarpetaInsegura=Ráfaga Studio solo se instala dentro de tu perfil (AppData\Local\Programs), donde ninguna otra cuenta del PC puede cambiar su código. Esta copia está en:%n%n%1%n%nDesinstálala (tus proyectos y claves de la carpeta «datos» se quedan: cópialos antes) y vuelve a abrir este instalador.
en.CarpetaInsegura=Ráfaga Studio is only installed inside your profile (AppData\Local\Programs), where no other account on this PC can change its code. This copy is in:%n%n%1%n%nUninstall it (your projects and keys in the “datos” folder stay: copy them first) and run this installer again.
pt.CarpetaInsegura=O Ráfaga Studio só é instalado dentro do seu perfil (AppData\Local\Programs), onde nenhuma outra conta do PC pode mudar o código. Esta cópia está em:%n%n%1%n%nDesinstale-a (seus projetos e chaves da pasta «datos» ficam: copie-os antes) e abra este instalador de novo.
fr.CarpetaInsegura=Ráfaga Studio ne s'installe que dans votre profil (AppData\Local\Programs), où aucun autre compte du PC ne peut modifier son code. Cette copie se trouve dans :%n%n%1%n%nDésinstallez-la (vos projets et clés du dossier « datos » restent : copiez-les d'abord) et relancez ce programme d'installation.
es.Abrir=Abrir Ráfaga Studio
en.Abrir=Open Ráfaga Studio
pt.Abrir=Abrir o Ráfaga Studio
fr.Abrir=Ouvrir Ráfaga Studio

[Tasks]
Name: "escritorio"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; La app: el código, las traducciones, los iconos, los ejemplos y los documentos legales (sin pruebas ni cachés)
Source: "..\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\mcp_server.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\modal_app.py"; DestDir: "{app}"; Flags: ignoreversion
; El lanzador (abre la app con el Python instalado) y el manifiesto con la huella de todo el código (Ráfaga Guardia)
Source: "..\Ráfaga Studio.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\integridad.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.lock"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-torch.lock"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\*.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\motor\*.py"; DestDir: "{app}\motor"; Flags: ignoreversion recursesubdirs
Source: "..\ui\*"; DestDir: "{app}\ui"; Excludes: "__pycache__,*.pyc"; Flags: ignoreversion recursesubdirs
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs
Source: "..\idiomas\*.json"; DestDir: "{app}\idiomas"; Flags: ignoreversion
Source: "..\ejemplos\*"; DestDir: "{app}\ejemplos"; Excludes: "__pycache__,*.pyc"; Flags: ignoreversion recursesubdirs
; Python portátil oficial, bajado y comprobado durante la instalación
Source: "https://api.nuget.org/v3-flatcontainer/python/{#PythonVersion}/python.{#PythonVersion}.nupkg"; \
  DestName: "python.zip"; DestDir: "{app}\python"; Hash: "{#PythonSha256}"; ExternalSize: {#PythonTamano}; \
  Flags: external download extractarchive recursesubdirs ignoreversion

[Icons]
; -E: un PYTHONPATH o PYTHONHOME que otro programa dejó en Windows no se mete en el Python de la app
Name: "{autoprograms}\{#Nombre}"; Filename: "{app}\python\tools\pythonw.exe"; Parameters: "-s -E ""{app}\app.py"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\icono.ico"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\python\tools\pythonw.exe"; Parameters: "-s -E ""{app}\app.py"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\icono.ico"; Tasks: escritorio

[Run]
Filename: "{app}\python\tools\pythonw.exe"; Parameters: "-s -E ""{app}\app.py"""; WorkingDir: "{app}"; \
  Description: "{cm:Abrir}"; Flags: nowait postinstall skipifsilent; Check: LibreriasListas

[UninstallRun]
; Antes de borrar Python: que Claude Code y Claude Desktop no sigan arrancando un python.exe de esta carpeta
Filename: "{app}\python\tools\python.exe"; Parameters: "-s -E -c ""from motor import conexion_mcp; conexion_mcp.desconectar_todo()"""; \
  WorkingDir: "{app}"; Flags: runhidden; RunOnceId: "QuitarMCP"

[UninstallDelete]
; Lo que no copió el instalador: Python con sus librerías y las cachés. Tus proyectos y claves (carpeta «datos») se
; quedan: bórralos a mano si quieres (ver PRIVACIDAD.md).
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\motor\__pycache__"
Type: filesandordirs; Name: "{app}\ui\__pycache__"
Type: filesandordirs; Name: "{app}\ui\paginas\__pycache__"

[Code]
var
  Listas: Boolean;
  Salida: String;

function LibreriasListas: Boolean;
begin
  Result := Listas;
end;

procedure VerLinea(const S: String; const Error, FirstLine: Boolean);
begin
  if Trim(S) <> '' then
  begin
    Salida := Salida + S + #13#10;
    if Length(Salida) > 1500 then  { solo las últimas líneas, que es donde pip dice el error }
      Salida := Copy(Salida, Length(Salida) - 1200, 1300);
    WizardForm.FilenameLabel.Caption := Copy(Trim(S), 1, 110);
  end;
  Log(S);
end;

function Pip(const Parametros: String): Boolean;
var
  Codigo: Integer;
begin
  Salida := '';
  { --isolated: el pip.ini y las PIP_* del usuario (require-virtualenv, user, target, otros índices) no cuentan.
    --only-binary: compilar un paquete bajaría sus herramientas de compilación sin hash (--require-hashes no las cubre) }
  Result := ExecAndLogOutput(ExpandConstant('{app}\python\tools\python.exe'),
    '-s -E -m pip install --isolated --no-cache-dir --only-binary :all: --disable-pip-version-check ' +
    '--no-warn-script-location ' +
    '--progress-bar off ' + Parametros,
    ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Codigo, @VerLinea) and (Codigo = 0);
end;

{ Solo dentro de tu perfil: también en las actualizaciones de una copia vieja, con /DIR= y en modo silencioso }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if Pos(Lowercase(AddBackslash(ExpandConstant('{localappdata}'))), Lowercase(AddBackslash(WizardDirValue))) <> 1 then
    Result := FmtMessage(CustomMessage('CarpetaInsegura'), [WizardDirValue]);
end;

{ Al actualizar, la app abierta (o el MCP que mantiene Claude) bloquea el Python de la app: Setup ofrece cerrarlos }
procedure RegisterExtraCloseApplicationsResources;
begin
  RegisterExtraCloseApplicationsResource(ExpandConstant('{app}\python\tools\pythonw.exe'));
  RegisterExtraCloseApplicationsResource(ExpandConstant('{app}\python\tools\python.exe'));
end;

{ Instalación desatendida: código 1 si faltan librerías, para que quien la lanzó se entere }
function GetCustomSetupExitCode: Integer;
begin
  if Listas then
    Result := 0
  else
    Result := 1;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep <> ssPostInstall then
    Exit;
  WizardForm.StatusLabel.Caption := CustomMessage('Librerias');
  WizardForm.ProgressGauge.Style := npbstMarquee;
  repeat
    { torch va aparte y solo desde el índice oficial de PyTorch (sin mezclar índices), como en Ráfaga Studio.bat }
    Listas := Pip('--require-hashes --no-deps -r requirements-torch.lock --index-url https://download.pytorch.org/whl/cpu')
      and Pip('--require-hashes -r requirements.lock');
  until Listas or WizardSilent or
    (MsgBox(FmtMessage(CustomMessage('FalloLibrerias'), [Salida]), mbError, MB_RETRYCANCEL) <> IDRETRY);
  WizardForm.ProgressGauge.Style := npbstNormal;
  if not Listas then
    SuppressibleMsgBox(CustomMessage('Incompleta'), mbInformation, MB_OK, IDOK);
end;
