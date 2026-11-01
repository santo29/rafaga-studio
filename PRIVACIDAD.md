# Aviso de privacidad de Ráfaga Studio

**Versión 10 · 29 de octubre de 2026** · Responsable: **Santo Montilla**, titular de la marca Ráfaga Studio™.

## Lo esencial

- **Ráfaga Studio se instala y trabaja en tu PC.** No tenemos servidores, no hay cuentas de Ráfaga Studio y no
  recogemos datos: ni analíticas, ni telemetría propia, ni informes de errores automáticos, ni publicidad. La app
  apaga además los avisos de uso que mandarían por su cuenta las librerías de Hugging Face y Gradio.
- **Tus proyectos, diseños, series, grabaciones y ajustes se guardan en tu PC** (casi todo en la carpeta `datos` de la
  app; abajo está el resto).
- **Tu cámara y tu micrófono solo se usan cuando tú los enciendes**, en «Grabarte» del editor de video: solo en tu PC,
  solo con ese panel abierto (el micrófono, solo mientras grabas) y se apagan al salir del panel o de la página.
  Windows enciende su luz de la cámara mientras está en uso. Lo grabado no sale de tu PC, salvo su sonido si
  pides subtítulos automáticos con Groq u OpenAI conectados (ver «Al transcribir»; sin clave, se transcribe en tu PC).
- **Tus claves de IA se guardan cifradas** con tu cuenta de Windows y cada una se envía solo al proveedor que le
  corresponde por su formato (las de Kling y Seedance, solo al que eliges con su botón «Conectar»).
- **Las funciones de IA usan servicios de internet.** Para crear, la app envía tus pedidos, textos, imágenes o audios
  directo al servicio que hace el trabajo, también cuando no conectaste ninguna clave (entonces usa servicios gratis de
  terceros). Además hay dos conexiones automáticas: al abrir la app se busca en PyPI una actualización de yt-dlp, y la
  primera vez, antes de mostrarte este aviso, se puede consultar a Cloudflare el país de tu conexión para elegir el
  idioma. Abajo está, una por una, qué se envía, a quién y cuándo.
- Nosotros no vemos ni recibimos nada de lo que haces. Lo que mandas a un servicio de terceros lo trata ese servicio,
  según su propia política de privacidad.

## Qué se guarda y dónde

Casi todo queda en la carpeta `datos` de Ráfaga Studio; lo demás, también en tu PC:

| Qué | Dónde |
|---|---|
| Tus claves de IA (cifradas con DPAPI, tu cuenta de Windows) | `datos/claves.json` |
| Copias cifradas de claves que no se pudieron leer | copias `datos/claves.danado-…` (una por cada vez que no se pudo leer) |
| Ajustes, idioma elegido, uso de cuotas gratis del día | `datos/ajustes.json`, `datos/idioma.json`, `datos/uso_nubes.json`, `datos/uso_nube.json` |
| Aceptación de este aviso (versión y fecha) | `datos/legal.json` |
| Videos, shorts, anuncios, canciones y grabaciones de la Cabina | `datos/proyectos/` |
| Proyectos del editor de video | `datos/ediciones/` |
| Lo que grabas con «Grabarte» (tu cámara y tu micrófono) | la carpeta `grabaciones` de cada proyecto, dentro de `datos/ediciones`. La app nunca las borra sola, tampoco al descartar un video sin guardar: bórralas tú cuando quieras |
| Diseños y tu marca (nombre, colores, logo) | `datos/disenos/`, `datos/marca.json`, `datos/marca/` |
| Series animadas, personajes y capítulos | `datos/series/` |
| Investigaciones de nichos | `datos/nichos/` |
| Lo que programaste en YouTube (archivo, hora, título e id del video) | `datos/publicaciones.json` |
| Tus preferencias que recuerda el Director (memoria del estudio: «títulos cortos», «mi marca es…») | `datos/memoria.json` |
| La conversación con el Director (lo que escribiste, las rutas de lo que adjuntaste, sus respuestas y qué archivos hizo; los últimos 100 mensajes). La borras con «Nueva conversación» | `datos/director.json` |
| Historial de Ráfaga Guardia: lo que la app frenó (fecha, tipo, gravedad, de dónde vino y un detalle corto sin claves, sin enlaces firmados y sin rutas enteras: de un archivo solo queda su nombre), si el estudio está bloqueado y la huella del archivo de claves (para notar si otro programa lo cambia). Guarda los últimos 500 eventos y lo borras con «Borrar historial» | `datos/guardia.json` |
| Videos exportados desde el editor | `Videos\Ráfaga Studio` |
| Diseños exportados | `Imágenes\Ráfaga Studio` (o donde elijas) |
| Conexión MCP (solo si la activas) | `.claude.json` en tu carpeta de usuario y `claude_desktop_config.json` en `AppData\Roaming\Claude` (sin copias: esa configuración lleva los tokens de tus otros servidores MCP). Al desinstalar la app, se quita |
| Modelos de IA locales | Whisper: la caché de Hugging Face (`.cache\huggingface` en tu carpeta de usuario). Demucs: `datos/modelos` (se comprueba su huella entera antes de cada uso) |
| Respuestas habladas del Director (temporales) | la carpeta temporal de Windows (`rafaga-voz`) |

Solo tu usuario de Windows puede leer tus claves: el cifrado DPAPI usa tu cuenta, así que copiadas a otro PC o a otra
cuenta no sirven. La carpeta `datos` nunca se sube al repositorio del proyecto.

## Qué sale de tu PC, a quién y cuándo

Nada de esto pasa por servidores nuestros: va directo de tu PC al servicio. OpenRouter y Pollinations son
intermediarios: reenvían tu pedido al proveedor del modelo que usan (por ejemplo OpenAI o Black Forest Labs).

| Cuándo | A quién | Qué se envía |
|---|---|---|
| Al conectar una clave en «Claves de IA» | El proveedor que le corresponde por su formato; Kling y Seedance, el que eliges con su botón «Conectar» (Kling: primero `api-singapore.klingai.com` y, solo si allí no la conocen, `api-beijing.klingai.com`, su región de China) | La clave, para comprobar que funciona (sin gastar nada) |
| Solo si pulsas «Explicar con IA» en un evento de Ráfaga Guardia | La IA de texto que conectaste; sin ninguna clave, la IA gratis de Pollinations | Ese evento y nada más: su fecha, tipo, gravedad, origen y el detalle corto ya limpio (sin claves, enlaces firmados ni rutas enteras). Lo que responde la IA solo se enseña: nunca hace nada |
| Al escribir guiones, diseñar, investigar o usar el Director | La IA de texto que conectaste (Anthropic, OpenAI, Google Gemini, Groq, OpenRouter, xAI, DeepSeek o Pollinations). Sin ninguna clave, la IA gratis de Pollinations | Tu pedido y el texto necesario para hacer el trabajo; en el Director, también la conversación, lo que devolvieron sus herramientas y las rutas de los archivos que adjuntas (en ellas se ve tu nombre de usuario de Windows). Las preferencias de la memoria del estudio viajan dentro de estos pedidos: todas al Director y, a cada especialista, las de todo el estudio y las de su departamento |
| Al crear imágenes (videos, anuncios, series, diseños) | La primera que funcione, empezando por la que elijas: Cloudflare, Pollinations, Hugging Face, Replicate, OpenAI, y Google Gemini solo si lo eliges en «Claves de IA» (de pago). Si no conectaste un token de Hugging Face, «Hugging Face» es un Space público. Al final, siempre, Pollinations sin clave. Aunque tengas claves, si la tuya falla se prueban las demás | La descripción de la imagen; con Gemini elegido, también tu foto de referencia (para mantener igual a la persona, el personaje o el producto) |
| En videos, anuncios y series con foto de referencia | OpenAI o Pollinations, si los conectaste | Tu foto de referencia, para mantener igual el producto, la persona o el personaje |
| Al crear videos animados con voz (es de pago) | La IA de «Escenas que hablan» en «Claves de IA»: en «Automático», Google (Gemini Omni) si conectaste Gemini; Kling o Seedance solo si los eliges ahí (ver la fila siguiente) | La descripción de cada escena y la frase que dice; tu foto de referencia si diste una. Para entregar el video, Google exige guardar la petición entera (texto, foto y video): la app borra la petición y el video de Google en cuanto termina, salga bien o mal. Si ese borrado falla (por ejemplo, sin internet), Google los guarda según su política (hasta 55 días). Solo se usa si tú lo pides: en Crear, marcando «Video animado con IA» (te dice el costo antes); con el Director o un agente MCP, cuando aceptas su costo |
| Al animar escenas o hacer escenas que hablan con Kling o Seedance (de pago; nunca en «Automático»: solo si los eliges en «Animar escenas con IA de video» o en «Escenas que hablan») | Kling AI (de Kuaishou), en la región de tu clave: con una clave global, `api-singapore.klingai.com` (contrato con Kling AI Pte. Ltd., Singapur); con una clave de su plataforma de China (klingai.com), `api-beijing.klingai.com` (Kuaishou, en China continental, con sus propias condiciones). Seedance en BytePlus ModelArk (de ByteDance), región Asia-Pacífico (`ark.ap-southeast.bytepluses.com`) | Cada imagen nueva de las escenas (también tu foto de referencia cuando es la primera escena) y la descripción del movimiento; en las escenas que hablan, también la frase que se dice. Con la clave global, Kling guarda los pedidos y respuestas 30 días y borra los videos a los 30 días; sus datos están en Singapur y, en la API de pago, no los usa para mejorar sus productos. Con una clave de China, dónde guarda tus datos, cuánto tiempo y para qué lo dicen las condiciones de esa plataforma, no las de Singapur. BytePlus procesa en Malasia, Indonesia o la UE, no entrena con tus datos sin tu permiso, deja el video 24 h para bajarlo y el registro de la tarea 7 días; lo que su filtro de contenido rechaza lo guarda 180 días en Malasia. Antes de cada trabajo la app te dice lo más que puede costar y no gasta sin tu sí; con un agente MCP, cuando aceptas su costo en la ventana de Ráfaga Studio |
| Al crear videos, anuncios, capítulos de serie o videos musicales, y al animar una imagen (de fábrica la IA de video está en «Automático») | Primero un Space público de Hugging Face (`zerogpu-aoti/wan2-2-fp8da-aoti-faster`), sin token. Si falla, tu nube Modal o Pollinations si los conectaste. Si eliges Modal, Pollinations, Kling o Seedance en «Claves de IA», el Space público no se usa. Con «No usar», no se envía nada | Cada imagen nueva de las escenas (también tu foto de referencia cuando es la primera escena) y la descripción del movimiento. A Pollinations solo va la descripción |
| Al pulsar «Crear mi avatar» en el editor de video (Avatar IA) | Tu nube Modal (la GPU de tu cuenta). Solo si esa vez marcas «Gratis con el Space público de Wan», el Space oficial de Hugging Face `Wan-AI/Wan2.2-S2V`, sin token, que llama a la API de Alibaba Cloud (DashScope) con la clave de su dueño. Nunca uno como respaldo del otro, y la casilla no se recuerda | Tu foto y el trozo de voz elegido (hasta 10 s en Modal; menos de 20 s en el Space). Al Space va una copia de la foto hecha de nuevo con solo sus píxeles: sin sus datos EXIF (como la ubicación GPS de una foto de móvil) ni el nombre del archivo. En Modal se procesan en tu cuenta y no se guardan (solo los pesos del modelo, en tu volumen). Con el Space, la foto y la voz se suben al almacenamiento de Alibaba Cloud (OSS), que guarda la tarea y el video 24 h; el dueño del Space también puede verlas. Con Modal, antes de gastar te dice lo que cuesta (unos US$0,35, como mucho US$0,95 por intento; si Modal interrumpe su GPU a medias, lo repite solo y ese intento se cobra aparte) |
| Al narrar (voz de los videos y respuestas del Director) | Servicio de voces de Microsoft Edge; o ElevenLabs si eliges una de sus voces | El texto que se va a leer |
| Al transcribir (subtítulos, shorts, video musical, escenas animadas con voz) | Groq u OpenAI si los conectaste; si no, se hace en tu PC | El audio (en los subtítulos automáticos del editor, también tu voz de «Grabarte»; en el video musical, también la letra, para acertar las palabras) |
| La primera vez que transcribes en tu PC o le hablas al Director | Hugging Face (`Systran/faster-whisper-small`) | Solo la descarga del modelo Whisper; tu audio no se envía |
| Al hablarle al Director | **Nadie: tu voz se entiende en tu PC** con Whisper | Nada de tu voz (el texto que dictaste sí va a tu IA de texto, como cualquier pedido al Director) |
| Cabina de grabación y separar voz y pista | **Nadie: se hace en tu PC** | Nada |
| Al grabarte en el editor de video («Grabarte»: tu cámara y tu micrófono) | **Nadie: se graba en tu PC** | Nada al grabar (si luego pides subtítulos automáticos con Groq u OpenAI conectados, el sonido de la grabación va a ese servicio: ver «Al transcribir»). La cámara se enciende solo cuando pulsas «Encender cámara» o «Grabar», y el micrófono solo mientras grabas; al salir del panel o de la página se apagan |
| La primera vez que separas voz y pista | Meta (`dl.fbaipublicfiles.com`) | Solo la descarga del modelo Demucs; tu canción no se envía |
| Al crear música | ElevenLabs o Google Gemini (Lyria) | Tu idea y la letra |
| Al programar en YouTube | Google (YouTube) | El video, título, descripción y etiquetas; tu permiso de YouTube se guarda cifrado en tu PC |
| Al sacar shorts, investigar nichos o crear anuncios | YouTube u otro sitio del enlace que pegaste; si tu IA de texto es Claude, su búsqueda web | El enlace, el tema buscado o el producto y su público |
| Si conectas Ráfaga Studio por MCP a Claude Code, Claude Desktop u otro agente | Ese agente y su proveedor (por ejemplo Anthropic) | Lo que devuelven las herramientas: rutas de tus archivos, títulos, descripciones, guiones y resultados de búsquedas |
| Al abrir la app la primera vez (antes de mostrar este aviso), si el idioma está en «Automático» y tu Windows está en inglés o en un idioma que la app no tiene | Cloudflare (`www.cloudflare.com/cdn-cgi/trace`) | Una consulta, que lleva tu IP, para saber el país de tu conexión, solo para elegir el idioma. Se guarda y no se repite, salvo que no haya internet o tu país no esté en la lista de la app: entonces se pregunta en cada arranque. Para evitarlo, elige un idioma fijo |
| Al instalar y cada vez que abres la app | PyPI (y, al instalar, PyTorch y NuGet de Microsoft, de donde se baja Python) | La descarga de las librerías y la actualización de yt-dlp; pip envía datos técnicos (versión de Windows y de Python) |

Protecciones que se aplican siempre:

- Cada clave se envía solo al proveedor que le corresponde por su formato, nunca a otro. Si pegas una clave de otro
  servicio con el mismo formato (por ejemplo de Stability o Moonshot, que empiezan por «sk-» como las antiguas de
  OpenAI), se mandaría a ese proveedor para comprobarla. Las claves de Seedance con su formato propio («ark-…») se
  reconocen solas. Las de Kling, y las de Seedance con el formato antiguo (un UUID, que usan muchos servicios), nunca se
  adivinan: van solo al servicio que eliges con su botón «Conectar», y ese botón rechaza una clave que parece de otro
  servicio.
- Las claves de Kling y Seedance solo viajan a la dirección fija de su API, nunca a una dirección que llegue en una
  respuesta; los videos se bajan de su servidor de descargas sin la clave.
- Tu token de Hugging Face nunca se envía a Spaces de terceros: se usan sin token.
- La app solo abre imágenes, audios y videos de este PC (nunca rutas de red ni otros archivos), así que no sirve para
  sacar documentos ni claves. Si un agente conectado por MCP pide usar una foto, un audio o un video de fuera de su
  carpeta (y de la de la app), Ráfaga Studio te lo pregunta antes en una ventana, nombrando cada archivo: si dices que
  sí, se envían a los servicios de la tabla.
- Lo que cuesta dinero, publica en tu canal o se guarda en la memoria del estudio, un agente MCP solo lo consigue con
  tu sí en una ventana de Ráfaga Studio, que el agente no puede leer ni contestar. Al publicar, la ventana dice qué
  video se sube y con qué título y descripción.
- El Director de la app solo usa los enlaces que escribiste tú y los archivos que le diste o que hizo el propio estudio.

Los Spaces públicos de Hugging Face y la opción sin clave de Pollinations son servicios abiertos: lo que se les envía
lo puede ver su dueño. En la IA de video los evitas eligiendo Modal, Pollinations, Kling, Seedance o «No usar» en
«Claves de IA». En las
imágenes, un token de Hugging Face evita el Space público, pero Pollinations sin clave queda siempre como último recurso
si fallan las demás.

## Lo que nunca hacemos

- No vendemos, alquilamos ni compartimos datos: no los tenemos.
- No ponemos publicidad ni rastreadores.
- No pedimos registro, correo ni datos personales para usar la app.
- No subimos tus archivos a ningún sitio que no salga en la tabla de arriba. Ojo: con la IA de video en «Automático»
  (como viene de fábrica), las imágenes de tus videos y anuncios, incluida tu foto de referencia, van a un Space público
  de Hugging Face. Si no lo quieres, elige Modal, Pollinations, Kling o Seedance (de pago) o «No usar» en «Claves de
  IA».

## Servicios de terceros

Cuando usas un servicio de IA, lo que le envías queda sujeto a su política de privacidad y a sus condiciones. Te
recomendamos leer las de los que conectes: Anthropic, OpenAI, Google (Gemini), Groq, OpenRouter, xAI, DeepSeek,
Cloudflare, Hugging Face, Pollinations, Replicate, Modal, ElevenLabs, Kling AI (Kuaishou), BytePlus (ByteDance, para
Seedance) y Microsoft (voces de Edge). Algunos servicios
gratis pueden usar lo que les envías para mejorar sus modelos: si trabajas con material confidencial de un cliente,
usa proveedores de pago que no lo hagan.

## Tus derechos y cómo borrar tus datos

Tus datos están en tu PC y los controlas tú:

- **Borrar todo:** cierra la app, desconecta el MCP en «Conexión MCP», borra la carpeta `datos` y, si quieres, las
  carpetas «Ráfaga Studio» de Videos e Imágenes y la caché de Whisper (`.cache\huggingface`).
- **Borrar tus grabaciones de cámara:** borra la carpeta `grabaciones` dentro de cada proyecto de `datos/ediciones`.
- **Borrar una clave:** quítala en «Claves de IA» y, si quieres, anúlala también en la web de su proveedor.
- **Borrar lo que recuerda el Director:** en el Director, «Memoria del estudio». Nunca guarda claves, contraseñas,
  tarjetas ni números de cuenta: los rechaza.
- **Desinstalar:** desconecta el MCP y luego desinstala Ráfaga Studio (o borra su carpeta).
- Para lo que enviaste a un servicio de terceros, ejerce tus derechos (acceso, borrado, oposición) ante ese servicio.

## Menores

Ráfaga Studio no está pensada para menores de edad sin la supervisión de un adulto responsable. Los servicios de IA de
terceros tienen sus propias edades mínimas.

## Seguridad

Ciframos tus claves con la cuenta de Windows. Comprobamos que cada archivo que abres sea de verdad lo que dice ser y
que los enlaces vayan a sitios públicos (si usas un proxy «fake-ip» como Clash y lo activas en «Claves de IA», esa
comprobación ya no puede frenar tu red local). Fijamos las versiones de las librerías con su huella digital, salvo
yt-dlp y su componente yt-dlp-ejs, que se actualizan solos al abrir la app (solo versiones ya compiladas y publicadas
hace 7 días o más), y el motor de video que se instala en tu propia nube Modal si la conectas (también con versiones
ya compiladas y de hace 7 días o más). Revisamos el código con
pruebas automáticas de seguridad. **Ráfaga Guardia**, dentro de la app, apunta en tu PC lo que se frena, comprueba
que el código de la app es el que instalaste y, si un agente insiste o el código cambió, bloquea el video, las
imágenes, la música y la voz de pago, publicar, la memoria y el MCP hasta que lo desbloquees tú (detalles en la [política de seguridad](SECURITY.md)). Protege la app y lo que
guarda, no el PC entero: ningún programa es infalible, mantén tu Windows y tu antivirus al día.

## Leyes aplicables

Este aviso sigue los principios de la Ley 172-13 de la República Dominicana sobre protección de datos personales. Si
vives en la Unión Europea, en el Reino Unido o en otro país con leyes de privacidad, también se aplican tus derechos
locales: como Ráfaga Studio no trata tus datos en servidores propios, cada proveedor que elijas responde por lo que le
envías.

## Cambios en este aviso

Si cambia lo que la app hace con tus datos, actualizaremos este aviso y su versión. La app te lo mostrará otra vez
antes de seguir.

Para cualquier duda o petición sobre privacidad, usa los canales de contacto de la [política de seguridad](SECURITY.md#contacto).
