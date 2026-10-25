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
; Los términos de la página de licencia: TERMINOS.md pasado a RTF en cada compilación (instalador\licencia.py). Con el .md
; tal cual, Inno enseñaba «## 9.», asteriscos y frases cortadas a la mitad; TERMINOS.md sigue siendo la única fuente.
#if Exec(AddBackslash(SourcePath) + "..\.venv\Scripts\python.exe", "-s -E instalador\licencia.py", AddBackslash(SourcePath) + "..", 1, 0) != 0
  #error No se pudo generar dist\licencia.rtf: ejecuta .venv\Scripts\python.exe -s -E instalador\licencia.py y mira el error
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
; Lo que enseñan Propiedades y el Administrador de tareas (sin esto, «Ráfaga Studio Setup», en inglés)
VersionInfoDescription=Instalador de {#Nombre}
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
LicenseFile=..\dist\licencia.rtf
; El registro de la instalación (%TEMP%\Setup Log …): ahí queda la salida completa de pip si algo falla
SetupLogging=yes
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

[Messages]
; Solo los mensajes de las páginas que de verdad salen (sin bienvenida, carpeta ni grupo). Los .isl de serie traen en
; español mayúsculas a la inglesa («Acuerdo de Licencia»), «seguro que» (es «seguro de que») y «usted», cuando el resto
; del instalador y de la app habla de tú; en portugués, «pra». Y lo que se acepta son unos términos de uso, no una licencia.
es.SelectLanguageTitle=Idioma de la instalación
es.SelectLanguageLabel=Elige el idioma de la instalación.
es.ExitSetupTitle=Salir de la instalación
es.ExitSetupMessage=La instalación no ha terminado. Si sales ahora, Ráfaga Studio no quedará instalado.%n%nPuedes volver a abrir este instalador cuando quieras para terminarla.%n%n¿Salir de la instalación?
es.WizardLicense=Términos de uso
es.LicenseLabel=Lee los términos antes de seguir.
es.LicenseLabel3=Para instalar Ráfaga Studio tienes que aceptar estos términos de uso.
es.LicenseAccepted=A&cepto los términos
es.LicenseNotAccepted=&No los acepto
es.WizardSelectTasks=Tareas adicionales
es.SelectTasksDesc=¿Qué más quieres que haga el instalador?
es.SelectTasksLabel2=Elige lo que quieres y pulsa Siguiente.
es.WizardReady=Listo para instalar
es.ReadyLabel1=Todo listo para instalar [name] en tu PC.
es.ReadyLabel2a=Pulsa Instalar para seguir, o Atrás si quieres cambiar algo.
es.ReadyLabel2b=Pulsa Instalar para seguir.
es.ReadyMemoTasks=Tareas adicionales:
es.DiskSpaceWarningTitle=Falta espacio en el disco
es.DiskSpaceWarning=La instalación necesita al menos %1 KB libres, pero el disco elegido solo tiene %2 KB.%n%n¿Quieres seguir de todas formas?
es.StopDownload=¿Seguro que quieres detener la descarga?
es.ErrorDownloadFailed=No se pudo descargar: %1 %2
es.ErrorDownloadSizeFailed=No se pudo saber el tamaño de la descarga: %1 %2
es.StopExtraction=¿Seguro que quieres detener la extracción?
es.ErrorExtractionFailed=No se pudo extraer: %1
es.WizardPreparing=Preparando la instalación
es.PreparingDesc=El instalador se está preparando para instalar [name] en tu PC.
es.ApplicationsFound=Estos programas están usando archivos que el instalador tiene que actualizar. Lo mejor es dejar que el instalador los cierre.
es.ApplicationsFound2=Estos programas están usando archivos que el instalador tiene que actualizar. Lo mejor es dejar que el instalador los cierre; al terminar, intentará volver a abrirlos.
es.InstallingLabel=Espera mientras se instala [name] en tu PC.
es.FinishedHeadingLabel=[name] ya está instalado
es.FinishedLabelNoIcons=La instalación de [name] terminó.
es.FinishedLabel=La instalación de [name] terminó. Puedes abrirlo con sus accesos directos.
es.ClickFinish=Pulsa Finalizar para cerrar el instalador.
es.ConfirmUninstall=¿Seguro que quieres desinstalar %1? Tus proyectos y claves (la carpeta «datos») se quedan en tu PC.
es.UninstallStatusLabel=Espera mientras se desinstala %1 de tu PC.
es.WizardUninstalling=Desinstalando
es.UninstalledAll=%1 se desinstaló de tu PC.
es.UninstalledMost=%1 se desinstaló.%n%nAlgunos elementos no se pudieron quitar (por ejemplo, tu carpeta «datos»): bórralos a mano si quieres.
pt.SelectLanguageTitle=Idioma do instalador
pt.SelectLanguageLabel=Escolha o idioma da instalação.
pt.ExitSetupTitle=Sair do instalador
pt.ExitSetupMessage=A instalação não terminou. Se você sair agora, o Ráfaga Studio não ficará instalado.%n%nVocê pode abrir este instalador de novo quando quiser para terminar.%n%nSair do instalador?
pt.WizardLicense=Termos de uso
pt.LicenseLabel=Leia os termos antes de continuar.
pt.LicenseLabel3=Para instalar o Ráfaga Studio, você precisa aceitar estes termos de uso (em espanhol).
pt.LicenseAccepted=Eu &aceito os termos
pt.LicenseNotAccepted=Eu &não aceito os termos
pt.WizardSelectTasks=Tarefas adicionais
pt.SelectTasksDesc=O que mais o instalador deve fazer?
pt.SelectTasksLabel2=Escolha o que você quer e clique em Avançar.
pt.WizardReady=Pronto para instalar
pt.ReadyLabel1=Tudo pronto para instalar o [name] no seu PC.
pt.ReadyLabel2a=Clique em Instalar para continuar, ou em Voltar se quiser mudar algo.
pt.ReadyLabel2b=Clique em Instalar para continuar.
pt.ReadyMemoTasks=Tarefas adicionais:
pt.DiskSpaceWarningTitle=Falta espaço no disco
pt.StopDownload=Tem certeza de que quer parar o download?
pt.ErrorDownloadFailed=Não foi possível baixar: %1 %2
pt.ErrorDownloadSizeFailed=Não foi possível saber o tamanho do download: %1 %2
pt.StopExtraction=Tem certeza de que quer parar a extração?
pt.ErrorExtractionFailed=Não foi possível extrair: %1
pt.WizardPreparing=Preparando a instalação
pt.PreparingDesc=O instalador está se preparando para instalar o [name] no seu PC.
pt.ApplicationsFound=Estes programas estão usando arquivos que o instalador precisa atualizar. O melhor é deixar o instalador fechá-los.
pt.ApplicationsFound2=Estes programas estão usando arquivos que o instalador precisa atualizar. O melhor é deixar o instalador fechá-los; ao terminar, ele tentará abri-los de novo.
pt.InstallingLabel=Aguarde enquanto o [name] é instalado no seu PC.
pt.FinishedHeadingLabel=O [name] foi instalado
pt.FinishedLabelNoIcons=A instalação do [name] terminou.
pt.FinishedLabel=A instalação do [name] terminou. Você pode abri-lo pelos atalhos.
pt.ClickFinish=Clique em Concluir para fechar o instalador.
pt.RetryCancelRetry=&Tentar novamente
pt.ConfirmUninstall=Tem certeza de que quer desinstalar o %1? Seus projetos e chaves (a pasta “datos”) ficam no seu PC.
pt.UninstallStatusLabel=Aguarde enquanto o %1 é desinstalado do seu PC.
pt.WizardUninstalling=Desinstalando
pt.UninstalledAll=O %1 foi desinstalado do seu PC.
pt.UninstalledMost=O %1 foi desinstalado.%n%nAlguns itens não puderam ser removidos (por exemplo, sua pasta “datos”): apague-os à mão se quiser.
; TERMINOS.md solo existe en español: el título y la frase de aceptación lo dicen
en.WizardLicense=Terms of use
en.LicenseLabel3=Please read the terms of use (in Spanish). You must accept them to install Ráfaga Studio.
en.LicenseAccepted=I &accept the terms
en.LicenseNotAccepted=I &do not accept the terms
fr.WizardLicense=Conditions d'utilisation
fr.LicenseLabel3=Veuillez lire les conditions d'utilisation (en espagnol). Vous devez les accepter pour installer Ráfaga Studio.
fr.LicenseAccepted=J'&accepte les conditions
fr.LicenseNotAccepted=Je &refuse les conditions

[CustomMessages]
es.Librerias=Instalando las librerías de IA (unos 1,5 GB; puede tardar de 10 a 30 minutos según tu internet)…
en.Librerias=Installing the AI libraries (about 1.5 GB; it can take 10 to 30 minutes depending on your internet)…
pt.Librerias=Instalando as bibliotecas de IA (cerca de 1,5 GB; pode levar de 10 a 30 minutos conforme sua internet)…
fr.Librerias=Installation des bibliothèques d'IA (environ 1,5 Go ; 10 à 30 minutes selon votre connexion)…
es.FalloLibrerias=No se pudieron instalar las librerías (¿sin internet?).%n%n%1%n%nPulsa «Reintentar» para probar otra vez, o «Cancelar» y vuelve a abrir este instalador cuando tengas internet: seguirá donde se quedó. El detalle completo está en el registro de la instalación: un archivo «Setup Log» en tu carpeta temporal (AppData\Local\Temp).
en.FalloLibrerias=The libraries could not be installed (no internet?).%n%n%1%n%nClick “Try again” to retry, or “Cancel” and run this installer again when you are online: it will continue where it stopped. The full details are in the setup log: a “Setup Log” file in your temporary folder (AppData\Local\Temp).
pt.FalloLibrerias=Não foi possível instalar as bibliotecas (sem internet?).%n%n%1%n%nClique em “Tentar novamente” para tentar de novo, ou em “Cancelar” e abra este instalador de novo quando tiver internet: ele continua de onde parou. Os detalhes completos estão no registro da instalação: um arquivo “Setup Log” na sua pasta temporária (AppData\Local\Temp).
fr.FalloLibrerias=Les bibliothèques n'ont pas pu être installées (pas d'internet ?).%n%n%1%n%nCliquez sur « Recommencer » pour réessayer, ou sur « Annuler » et relancez ce programme d'installation une fois en ligne : il reprendra là où il s'est arrêté. Le détail complet se trouve dans le journal d'installation : un fichier « Setup Log » dans votre dossier temporaire (AppData\Local\Temp).
es.SinDetalle=El instalador de librerías no dio el motivo.
en.SinDetalle=The library installer did not give a reason.
pt.SinDetalle=O instalador de bibliotecas não deu o motivo.
fr.SinDetalle=Le programme d'installation des bibliothèques n'a pas donné la raison.
es.Libreria=Descargando %1…
en.Libreria=Downloading %1…
pt.Libreria=Baixando %1…
fr.Libreria=Téléchargement de %1…
es.Incompleta=Ráfaga Studio quedó instalado, pero le faltan librerías. Vuelve a abrir este instalador con internet para terminar.
en.Incompleta=Ráfaga Studio is installed, but some libraries are missing. Run this installer again when you are online to finish.
pt.Incompleta=O Ráfaga Studio foi instalado, mas faltam bibliotecas. Abra este instalador de novo com internet para terminar.
fr.Incompleta=Ráfaga Studio est installé, mais il manque des bibliothèques. Relancez ce programme d'installation une fois en ligne pour terminer.
es.CarpetaInsegura=Ráfaga Studio solo se instala dentro de tu perfil (AppData\Local\Programs), donde ninguna otra cuenta del PC puede cambiar su código. Esta copia está en:%n%n%1%n%nDesinstálala (tus proyectos y claves de la carpeta «datos» no se borran: cópialos luego a la nueva instalación) y vuelve a abrir este instalador.
en.CarpetaInsegura=Ráfaga Studio is only installed inside your profile (AppData\Local\Programs), where no other account on this PC can change its code. This copy is in:%n%n%1%n%nUninstall it (your projects and keys in the “datos” folder are not deleted: copy them to the new installation afterwards) and run this installer again.
pt.CarpetaInsegura=O Ráfaga Studio só é instalado dentro do seu perfil (AppData\Local\Programs), onde nenhuma outra conta do PC pode mudar o código. Esta cópia está em:%n%n%1%n%nDesinstale-a (seus projetos e chaves da pasta “datos” não são apagados: copie-os depois para a nova instalação) e abra este instalador de novo.
fr.CarpetaInsegura=Ráfaga Studio ne s'installe que dans votre profil (AppData\Local\Programs), où aucun autre compte du PC ne peut modifier son code. Cette copie se trouve dans :%n%n%1%n%nDésinstallez-la (vos projets et clés du dossier « datos » ne sont pas supprimés : copiez-les ensuite dans la nouvelle installation) et relancez ce programme d'installation.
es.Abrir=Abrir Ráfaga Studio
en.Abrir=Open Ráfaga Studio
pt.Abrir=Abrir o Ráfaga Studio
fr.Abrir=Ouvrir Ráfaga Studio

[Tasks]
Name: "escritorio"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Ráfaga Guardia: Inno no borra al actualizar lo que la versión nueva ya no trae. Un .py viejo en motor\ o ui\
; contaría como un módulo «de más» y bloquearía la app en cada arranque como si fuera malware. Se borra el código
; anterior antes de copiar el nuevo; reinstalar también quita así uno plantado (motor\x.py, un json.py o json.pyc en
; la raíz). Corre antes de [Files] y no toca «datos» (tus proyectos y claves) ni «python».
Type: filesandordirs; Name: "{app}\motor"
Type: filesandordirs; Name: "{app}\ui"
Type: files; Name: "{app}\*.py"
Type: files; Name: "{app}\*.pyw"
Type: files; Name: "{app}\*.pyc"
Type: files; Name: "{app}\*.pyd"

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
  Errores: String;

function LibreriasListas: Boolean;
begin
  Result := Listas;
end;

{ La salida de pip va entera al registro de la instalación (SetupLogging), pero no se enseña: en inglés y con URLs
  («Downloading torch-2.14.1%2Bcpu…», «Requirement already satisfied…»). Bajo la barra sale «Descargando sniffio…» y,
  si falla, solo sus líneas «ERROR». }
procedure VerLinea(const S: String; const Error, FirstLine: Boolean);
var
  Linea: String;
  Fin: Integer;
begin
  Log(S);
  Linea := Trim(S);
  if Pos('ERROR', Linea) = 1 then
  begin
    if Length(Errores) < 300 then
      Errores := Copy(Errores + Linea + #13#10, 1, 300);
  end
  else if Pos('Collecting ', Linea) = 1 then
  begin
    { «Collecting sniffio==1.3.1 (from -r requirements.lock (line 2588))» → «sniffio» }
    Linea := Copy(Linea, 12, Length(Linea));
    Fin := Pos('=', Linea);
    if Fin = 0 then
      Fin := Pos(' ', Linea);
    if Fin > 0 then
      Linea := Copy(Linea, 1, Fin - 1);
    WizardForm.FilenameLabel.Caption := FmtMessage(CustomMessage('Libreria'), [Linea]);
  end;
end;

{ El aviso de error con los botones en el idioma del instalador: los de MsgBox los pone Windows en el suyo, y con
  Windows en inglés el texto pedía «Reintentar» al lado de un botón «Retry». True si se quiere reintentar. }
function Reintentar: Boolean;
var
  Titulo, Mensaje: String;
  Corte: Integer;
  Botones: TArrayOfString;
begin
  Titulo := '';
  if Errores = '' then
    Errores := CustomMessage('SinDetalle');
  Mensaje := FmtMessage(CustomMessage('FalloLibrerias'), [Trim(Errores)]);
  Corte := Pos(#13#10#13#10, Mensaje);  { la primera frase va de título del aviso, si se puede separar }
  if Corte > 0 then
  begin
    Titulo := Copy(Mensaje, 1, Corte - 1);
    Mensaje := Copy(Mensaje, Corte + 4, Length(Mensaje));
  end;
  { (una línea que empieza por «[» es una sección para Inno: los botones van en su variable) }
  Botones := [SetupMessage(msgRetryCancelRetry), SetupMessage(msgRetryCancelCancel)];
  Result := TaskDialogMsgBox(Titulo, Mensaje, mbError, MB_RETRYCANCEL, Botones, 0) = IDRETRY;
end;

function Pip(const Parametros: String): Boolean;
var
  Codigo: Integer;
begin
  Errores := '';
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
    WizardForm.FilenameLabel.Caption := '';  { no se queda el último archivo copiado mientras pip empieza }
    { torch va aparte y solo desde el índice oficial de PyTorch (sin mezclar índices), como en Ráfaga Studio.bat }
    Listas := Pip('--require-hashes --no-deps -r requirements-torch.lock --index-url https://download.pytorch.org/whl/cpu')
      and Pip('--require-hashes -r requirements.lock');
  until Listas or WizardSilent or not Reintentar;
  WizardForm.ProgressGauge.Style := npbstNormal;
  if not Listas then
    SuppressibleMsgBox(CustomMessage('Incompleta'), mbInformation, MB_OK, IDOK);
end;
