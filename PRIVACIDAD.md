# Aviso de privacidad de Ráfaga Studio

**Versión 5 · 24 de octubre de 2026** · Responsable: **Santo Montilla**, titular de la marca Ráfaga Studio™.

## Lo esencial

- **Ráfaga Studio se instala y trabaja en tu PC.** No tenemos servidores, no hay cuentas de Ráfaga Studio y no
  recogemos datos: ni analíticas, ni telemetría propia, ni informes de errores automáticos, ni publicidad. La app
  apaga además los avisos de uso que mandarían por su cuenta las librerías de Hugging Face y Gradio.
- **Tus proyectos, diseños, series, grabaciones y ajustes se guardan en tu PC** (casi todo en la carpeta `datos` de la
  app; abajo está el resto).
- **Tus claves de IA se guardan cifradas** con tu cuenta de Windows y cada una se envía solo al proveedor que le
  corresponde por su formato.
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
| Copias cifradas de claves que no se pudieron leer | `datos/claves.danado-*` |
| Ajustes, idioma elegido, uso de cuotas gratis del día | `datos/ajustes.json`, `datos/idioma.json`, `datos/uso_nubes.json`, `datos/uso_nube.json` |
| Aceptación de este aviso (versión y fecha) | `datos/legal.json` |
| Videos, shorts, anuncios, canciones y grabaciones de la Cabina | `datos/proyectos/` |
| Proyectos del editor de video | `datos/ediciones/` |
| Diseños y tu marca (nombre, colores, logo) | `datos/disenos/`, `datos/marca.json`, `datos/marca/` |
| Series animadas, personajes y capítulos | `datos/series/` |
| Investigaciones de nichos | `datos/nichos/` |
| Lo que programaste en YouTube (archivo, hora, título e id del video) | `datos/publicaciones.json` |
| Tus preferencias que recuerda el Director (memoria del estudio: «títulos cortos», «mi marca es…») | `datos/memoria.json` |
| Videos exportados desde el editor | `Videos\Ráfaga Studio` |
| Diseños exportados | `Imágenes\Ráfaga Studio` (o donde elijas) |
| Conexión MCP (solo si la activas) | `%USERPROFILE%\.claude.json` y `%APPDATA%\Claude\claude_desktop_config.json`, con una copia `.bak-rafaga` |
| Modelos de IA locales (Whisper y Demucs) | `%USERPROFILE%\.cache\huggingface` y `%USERPROFILE%\.cache\torch` |
| Respuestas habladas del Director (temporales) | la carpeta temporal de Windows (`rafaga-voz`) |

Solo tu usuario de Windows puede leer tus claves: el cifrado DPAPI usa tu cuenta, así que copiadas a otro PC o a otra
cuenta no sirven. La carpeta `datos` nunca se sube al repositorio del proyecto.

## Qué sale de tu PC, a quién y cuándo

Nada de esto pasa por servidores nuestros: va directo de tu PC al servicio. OpenRouter y Pollinations son
intermediarios: reenvían tu pedido al proveedor del modelo que usan (por ejemplo OpenAI o Black Forest Labs).

| Cuándo | A quién | Qué se envía |
|---|---|---|
| Al conectar una clave en «Claves de IA» | El proveedor que le corresponde por su formato | La clave, para comprobar que funciona |
| Al escribir guiones, diseñar, investigar o usar el Director | La IA de texto que conectaste (Anthropic, OpenAI, Google Gemini, Groq, OpenRouter, xAI, DeepSeek o Pollinations). Sin ninguna clave, la IA gratis de Pollinations | Tu pedido y el texto necesario para hacer el trabajo; en el Director, también la conversación, lo que devolvieron sus herramientas y las rutas de los archivos que adjuntas (en ellas se ve tu nombre de usuario de Windows). Las preferencias de la memoria del estudio viajan dentro de estos pedidos: todas al Director y, a cada especialista, las de todo el estudio y las de su departamento |
| Al crear imágenes (videos, anuncios, series, diseños) | La primera que funcione, empezando por la que elijas: Cloudflare, Pollinations, Hugging Face, Replicate, OpenAI, y Google Gemini solo si lo eliges en «Claves de IA» (de pago). Si no conectaste un token de Hugging Face, «Hugging Face» es un Space público. Al final, siempre, Pollinations sin clave. Aunque tengas claves, si la tuya falla se prueban las demás | La descripción de la imagen; con Gemini elegido, también tu foto de referencia (para mantener igual a la persona, el personaje o el producto) |
| En videos, anuncios y series con foto de referencia | OpenAI o Pollinations, si los conectaste | Tu foto de referencia, para mantener igual el producto, la persona o el personaje |
| Al crear videos animados con voz (si conectaste Gemini; es de pago) | Google (Gemini Omni) | La descripción de cada escena y la frase que dice; tu foto de referencia si diste una. Para entregar el video, Google exige guardar la petición entera (texto, foto y video): la app borra la petición y el video de Google en cuanto termina, salga bien o mal. Si ese borrado falla (por ejemplo, sin internet), Google los guarda según su política (hasta 55 días). Solo se usa si tú lo pides: en Crear, marcando «Video animado con IA» (te dice el costo antes); con el Director o un agente MCP, cuando aceptas su costo |
| Al crear videos, anuncios, capítulos de serie o videos musicales, y al animar una imagen (de fábrica la IA de video está en «Automático») | Primero un Space público de Hugging Face (`zerogpu-aoti/wan2-2-fp8da-aoti-faster`), sin token. Si falla, tu nube Modal o Pollinations si los conectaste. Si eliges Modal o Pollinations en «Claves de IA», el Space público no se usa. Con «No usar», no se envía nada | Cada imagen nueva de las escenas (también tu foto de referencia cuando es la primera escena) y la descripción del movimiento. A Pollinations solo va la descripción |
| Al narrar (voz de los videos y respuestas del Director) | Servicio de voces de Microsoft Edge; o ElevenLabs si eliges una de sus voces | El texto que se va a leer |
| Al transcribir (subtítulos, shorts, video musical, escenas animadas con voz) | Groq u OpenAI si los conectaste; si no, se hace en tu PC | El audio (en el video musical, también la letra, para acertar las palabras) |
| La primera vez que transcribes en tu PC o le hablas al Director | Hugging Face (`Systran/faster-whisper-small`) | Solo la descarga del modelo Whisper; tu audio no se envía |
| Al hablarle al Director | **Nadie: tu voz se entiende en tu PC** con Whisper | Nada de tu voz (el texto que dictaste sí va a tu IA de texto, como cualquier pedido al Director) |
| Cabina de grabación y separar voz y pista | **Nadie: se hace en tu PC** | Nada |
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
  OpenAI), se mandaría a ese proveedor para comprobarla.
- Tu token de Hugging Face nunca se envía a Spaces de terceros: se usan sin token.
- La app solo abre imágenes, audios y videos de este PC (nunca rutas de red ni otros archivos), así que no sirve para
  sacar documentos ni claves. Ojo: un agente conectado por MCP sí puede pedirle que use cualquier foto, audio o video de
  tu PC, y esos se envían a los servicios de la tabla.
- El Director de la app solo usa los enlaces que escribiste tú y los archivos que le diste o que hizo el propio estudio.

Los Spaces públicos de Hugging Face y la opción sin clave de Pollinations son servicios abiertos: lo que se les envía
lo puede ver su dueño. En la IA de video los evitas eligiendo Modal, Pollinations o «No usar» en «Claves de IA». En las
imágenes, un token de Hugging Face evita el Space público, pero Pollinations sin clave queda siempre como último recurso
si fallan las demás.

## Lo que nunca hacemos

- No vendemos, alquilamos ni compartimos datos: no los tenemos.
- No ponemos publicidad ni rastreadores.
- No pedimos registro, correo ni datos personales para usar la app.
- No subimos tus archivos a ningún sitio que no salga en la tabla de arriba. Ojo: con la IA de video en «Automático»
  (como viene de fábrica), las imágenes de tus videos y anuncios, incluida tu foto de referencia, van a un Space público
  de Hugging Face. Si no lo quieres, elige Modal, Pollinations o «No usar» en «Claves de IA».

## Servicios de terceros

Cuando usas un servicio de IA, lo que le envías queda sujeto a su política de privacidad y a sus condiciones. Te
recomendamos leer las de los que conectes: Anthropic, OpenAI, Google (Gemini), Groq, OpenRouter, xAI, DeepSeek,
Cloudflare, Hugging Face, Pollinations, Replicate, Modal, ElevenLabs y Microsoft (voces de Edge). Algunos servicios
gratis pueden usar lo que les envías para mejorar sus modelos: si trabajas con material confidencial de un cliente,
usa proveedores de pago que no lo hagan.

## Tus derechos y cómo borrar tus datos

Tus datos están en tu PC y los controlas tú:

- **Borrar todo:** cierra la app, desconecta el MCP en «Conexión MCP», borra la carpeta `datos` y, si quieres, las
  carpetas «Ráfaga Studio» de Videos e Imágenes y las cachés de modelos (`.cache\huggingface` y `.cache\torch`).
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
que los enlaces vayan a sitios públicos. Fijamos las versiones de las librerías con su huella digital, salvo yt-dlp, que
se actualiza sola al abrir la app (solo versiones ya compiladas y publicadas hace 7 días o más), y el motor de video
que se instala en tu propia nube Modal si la conectas. Revisamos el código con
pruebas automáticas de seguridad. Ningún programa es infalible: mantén tu Windows y tu antivirus al día.

## Leyes aplicables

Este aviso sigue los principios de la Ley 172-13 de la República Dominicana sobre protección de datos personales. Si
vives en la Unión Europea, en el Reino Unido o en otro país con leyes de privacidad, también se aplican tus derechos
locales: como Ráfaga Studio no trata tus datos en servidores propios, cada proveedor que elijas responde por lo que le
envías.

## Cambios en este aviso

Si cambia lo que la app hace con tus datos, actualizaremos este aviso y su versión. La app te lo mostrará otra vez
antes de seguir.

Para cualquier duda o petición sobre privacidad, usa los canales de contacto de [SECURITY.md](SECURITY.md#contacto).
