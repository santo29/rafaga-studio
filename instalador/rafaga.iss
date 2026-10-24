; Instalador de Ráfaga Studio (Inno Setup 7): compílalo con  ISCC instalador\rafaga.iss  -> dist\RafagaStudio-Setup-<versión>.exe
;
; Instalador ligero: lleva la app (unos MB) y, al instalar, baja de sus fuentes oficiales:
; - Python (el paquete «python» de NuGet, de la Python Software Foundation: portátil, no se registra en Windows),
;   comprobando su huella SHA-256;
; - las librerías, con pip y las mismas versiones y huellas que requirements.lock (nada distinto de lo probado entra).
; Se instala solo para tu usuario (sin permisos de administrador), así la carpeta «datos» de la app se puede escribir.

#define Nombre "Ráfaga Studio"
#define Version "1.0.0"
#define Titular "Santo Montilla"
#define PythonVersion "3.14.9"
#define PythonSha256 "7cd9d07aec975212344dc6f7e45019378cf6775dd564181e269010a1eddaaec7"
#define PythonTamano "15568326"

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
Source: "..\requirements.lock"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-torch.lock"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\*.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\motor\*.py"; DestDir: "{app}\motor"; Flags: ignoreversion
Source: "..\ui\*"; DestDir: "{app}\ui"; Excludes: "__pycache__,*.pyc"; Flags: ignoreversion recursesubdirs
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs
Source: "..\idiomas\*.json"; DestDir: "{app}\idiomas"; Flags: ignoreversion
Source: "..\ejemplos\*"; DestDir: "{app}\ejemplos"; Excludes: "__pycache__,*.pyc"; Flags: ignoreversion recursesubdirs
; Python portátil oficial, bajado y comprobado durante la instalación
Source: "https://api.nuget.org/v3-flatcontainer/python/{#PythonVersion}/python.{#PythonVersion}.nupkg"; \
  DestName: "python.zip"; DestDir: "{app}\python"; Hash: "{#PythonSha256}"; ExternalSize: {#PythonTamano}; \
  Flags: external download extractarchive recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#Nombre}"; Filename: "{app}\python\tools\pythonw.exe"; Parameters: """{app}\app.py"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\icono.ico"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\python\tools\pythonw.exe"; Parameters: """{app}\app.py"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\icono.ico"; Tasks: escritorio

[Run]
Filename: "{app}\python\tools\pythonw.exe"; Parameters: """{app}\app.py"""; WorkingDir: "{app}"; \
  Description: "{cm:Abrir}"; Flags: nowait postinstall skipifsilent; Check: LibreriasListas

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
  Result := ExecAndLogOutput(ExpandConstant('{app}\python\tools\python.exe'),
    '-m pip install --no-cache-dir --disable-pip-version-check --no-warn-script-location --progress-bar off ' + Parametros,
    ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Codigo, @VerLinea) and (Codigo = 0);
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
    MsgBox(CustomMessage('Incompleta'), mbInformation, MB_OK);
end;
