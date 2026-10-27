<div align="center">

<img src="assets/icono.png" width="96" alt="Logo de Ráfaga Studio">

# Ráfaga Studio

**Estudio creativo con IA para Windows, hecho para quien no sabe programar.**<br>
Lo instalas como cualquier programa, pegas una clave y la app reconoce sola de qué servicio es.<br>
Pides un video en una frase y te entrega el guion, las escenas, la voz, los subtítulos y el montaje.

[![Descargar para Windows 10/11](https://img.shields.io/badge/Descargar_para_Windows_10%2F11-gratis-7c5cff?style=for-the-badge)](https://github.com/santo29/rafaga-studio/releases/latest)

[![Sin programar](https://img.shields.io/badge/sin_programar-instala%2C_pega_tu_clave%2C_crea-22c55e)](#-sin-saber-programar-tu-primer-video-en-5-minutos)
[![Motor: MIT](https://img.shields.io/badge/motor-MIT-22c55e)](LICENSE)
[![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078d4)](#-sin-saber-programar-tu-primer-video-en-5-minutos)
[![Servidor MCP](https://img.shields.io/badge/MCP-17%20herramientas-7c5cff)](#-úsalo-desde-claude-mcp)
[![Idiomas](https://img.shields.io/badge/idiomas-ES%20%C2%B7%20EN%20%C2%B7%20PT%20%C2%B7%20FR-f59e0b)](idiomas)

[**▶ Ver la demo**](ejemplos/presentacion-app.mp4) ·
[**▶ Ver el anuncio**](ejemplos/anuncio-rafaga.mp4) ·
[**🇬🇧 Read in English**](README.md)

<a href="ejemplos/presentacion-app.mp4"><img src="ejemplos/presentacion-app.gif" width="640" alt="Video de presentación de Ráfaga Studio"></a>

<sub>Esta demo la montó el propio editor de Ráfaga Studio. El guion lo escribió Claude como Director del estudio.</sub>

<a href="ejemplos/anuncio-rafaga.mp4"><img src="ejemplos/anuncio-rafaga.gif" width="640" alt="Anuncio de Ráfaga Studio: Tu PC. Tu estudio."></a>

<sub>El anuncio «Tu PC. Tu estudio.» (<a href="ejemplos/anuncio-rafaga-en.mp4">en inglés</a>), en 4K, también hecho con el
estudio: las personas y sus voces son ficticias, hechas con IA, con la app real en sus pantallas, y la música es una
canción hecha con Ráfaga Studio.</sub>

</div>

---

Ráfaga Studio es un **generador de videos con IA** para tu PC: de texto a video, shorts para TikTok, Reels y YouTube,
anuncios con la foto de tu producto, canciones, diseños en 4K y dibujos animados, con un **Director IA al que le hablas**.
No hay que escribir código ni abrir una consola: todo se hace con botones, en **español**, inglés, portugués o
francés. Lo gratis va primero, y lo de pago solo se usa si tú lo eliges.

## 🚀 Sin saber programar: tu primer video en 5 minutos

Los 5 minutos son lo que haces tú, contando desde que la app ya está instalada. La instalación baja unos 1,5 GB y
tarda de 10 a 30 minutos según tu internet, y en el modo gratis el video puede tardar más en salir, porque los
servicios gratis atienden por turno.

**Necesitas:** Windows 10 u 11 de 64 bits, unos 3 GB libres e internet. No hace falta tarjeta gráfica.

### 1. Descarga e instala

1. Baja `RafagaStudio-Setup-1.0.0.exe` (unos 42 MB) de [Versiones](https://github.com/santo29/rafaga-studio/releases/latest)
   y ábrelo. En «Assets», pulsa `RafagaStudio-Setup-1.0.0.exe` (no «Source code»). Si el navegador dice que el
   archivo no se descarga con frecuencia, pulsa «…» y «Conservar».
2. **Windows te muestra un aviso azul: «Windows protegió su PC».** Sale porque el instalador todavía no lleva firma
   digital. Pulsa **«Más información»** y después **«Ejecutar de todas formas»**. Este aviso es de Windows, no de la
   app. No te pedirá permisos de administrador: se instala solo para tu cuenta.
3. Elige el idioma, lee los términos, marca **«Acepto los términos»** y sigue. No tienes que elegir carpeta. Deja
   marcada **«Crear un acceso directo en el escritorio»**, pulsa **Siguiente** y después **Instalar**.
4. El instalador baja por su cuenta Python (el programa con el que funciona la app) y las librerías de IA, y
   comprueba la huella de cada archivo. La barra avanza sola y debajo va diciendo qué descarga. Si se corta
   internet, pulsa **«Reintentar»**, o vuelve a abrir el instalador más tarde: sigue donde se quedó.
5. Al terminar, deja marcada **«Abrir Ráfaga Studio»** y pulsa **Finalizar**.

### 2. Ábrelo

La primera vez sale **«Bienvenido a Ráfaga Studio»**, con lo importante sobre tu privacidad en cuatro puntos: no hay
servidores ni cuentas, tus claves quedan cifradas en tu PC, qué servicios gratis reciben tus pedidos y que uses
contenido propio. Pulsa **«✨ Acepto, empezar»**.

La app sale en el idioma de tu PC. Si quieres otro, cámbialo abajo del menú lateral.

### 3. Crea tu primer video, sin ninguna clave

1. Pulsa **«✨ Crear con IA»** en el menú, o la tarjeta **«Crear video»** de Inicio.
2. Escribe tu idea, por ejemplo: *5 datos impactantes sobre el océano profundo, tono misterioso*.
3. Deja lo demás como viene: vertical 9:16, estilo «Automático», la voz gratis y 45 segundos. En español la voz es
   la de Emilio (República Dominicana); también hay voces de Puerto Rico, Cuba, México y España.
4. Pulsa **«✨ Generar video»**. Como no hay nada de pago, no te pide aprobar ningún costo. Verás una barra con lo que
   va haciendo, escena por escena.
5. Si un servicio gratis falla, el video sale igual: con la imagen anterior, o con un zoom suave en vez de
   movimiento. Al final te dice qué pasó. Sin claves el video sale más simple: pocas imágenes nuevas (las demás
   escenas repiten la anterior con zoom suave). Para un primer video mucho mejor, conecta antes Groq y Cloudflare
   (gratis, unos 2 minutos): mira [«Tu primera clave»](#-tu-primera-clave-copiar-y-pegar).
6. El video aparece en el reproductor. **«Abrir carpeta»** te lleva al archivo, **«Copiar texto para publicar»** te
   da el texto para tu red social y **«✂️ Editar»** lo pasa al editor.

Sin claves, el estudio piensa con una IA gratis más lenta; el Director te lo dice en su chat al abrir la app y te
aconseja conectar Groq o Gemini (gratis) en «Claves de IA». Eso es lo siguiente.

## 🔑 Tu primera clave: copiar y pegar

Una clave de API es una contraseña que te da cada servicio de IA para que la app trabaje con tu cuenta. Conseguirla y
ponerla no requiere saber programar:

1. Abre **«🔑 Claves de IA»** en el menú.
2. En la lista **«Servicios que puedes conectar»**, pulsa **«Conseguir clave ↗»** del servicio que quieras: se abre
   la página donde se crea. Créala y cópiala.
3. Pégala en el cuadro de arriba y pulsa **«Conectar»** (o Enter). Es un solo cuadro para todas: la app **reconoce
   sola de qué servicio es**, la comprueba y la suma a la lista. Lo que pegas sale oculto; «Ver lo que pegué» lo
   enseña para revisar que entró entera.

Las claves se guardan cifradas y solo en tu PC. Puedes conectar varias, y cada una se usa para lo suyo.

**Las primeras que conviene conectar:**

| Servicio | Qué te da | Precio |
|---|---|---|
| Groq | Guiones con IA rápidos (sin clave van lentos) y transcripción rápida | Gratis |
| Cloudflare Workers AI | Unas 100 imágenes al día. Pega juntos el ID de cuenta y el token | Gratis |
| Pollinations | Imágenes y guiones sin marca de agua | Gratis |
| Gemini (Google) | Guiones gratis. Si lo eliges: imágenes Nano Banana, videos animados con voz y música con Lyria | Gratis (lo demás, de pago) |
| Modal | Tu propia nube de video con IA (Wan 2.2): las escenas se mueven de verdad. Pega las dos partes del token (`ak-…` y `as-…`) y pulsa «Instalar motor en Modal» | US$1 gratis al mes, o US$30 gratis al mes si añades tarjeta (pon un límite de US$30 en Modal y no pagas nada) |
| ElevenLabs | Voces realistas y música | Plan gratis pequeño |

Sin ninguna clave funciona casi todo. Necesitan clave la música con IA (ElevenLabs o Gemini) y los personajes que
hablan con los labios sincronizados (Gemini, Kling o Seedance, de pago). Publicar en YouTube pide crear una vez tu app
de Google; la app trae la guía.

**¿Funciona cada clave?** Pulsa **«Comprobar conexiones»**: cada servicio sale con su estado («Funciona», «La clave
vale», «Sin saldo», «Falta un permiso», «Clave no válida», «Sin cuota ahora»…) y, si algo falla, qué hacer en una
frase, por ejemplo dónde recargar. En algunos servicios (Claude, OpenAI, Modal…) el saldo solo se sabe al usarlos:
la comprobación dice «La clave vale» y, si falta saldo, lo verás en el primer trabajo y en «Actividad de la IA».

## ❓ Preguntas frecuentes

**¿Es gratis?**
La app no te cobra nada: no tiene cuentas, suscripción ni pagos dentro. Puedes usarla para tu contenido, también con
fines comerciales (ver los [Términos](TERMINOS.md)). Sin ninguna clave ya hace guiones, imágenes, animación (con la
cuota gratis de un Space público de Hugging Face, unos minutos al día), voces, subtítulos y edición. Lo de pago
(Gemini, ElevenLabs, Kling, Seedance…) solo se usa si lo eliges, y antes te dice lo más que puede costar. Ojo: las
voces gratis de Microsoft Edge no garantizan el uso comercial; para eso, usa una voz con licencia comercial.

**¿Necesito un PC potente?**
No hace falta tarjeta gráfica. Las imágenes y la animación se hacen en servicios de internet o en tu nube Modal. En tu
PC se monta el video y se hacen la transcripción (Whisper) y la separación de voz y pista (Demucs), con el procesador.
Pide Windows 10 u 11 de 64 bits, unos 3 GB libres e internet.

**¿Mi clave está segura?**
Se guarda cifrada con tu cuenta de Windows (DPAPI), solo en tu PC: solo tu usuario puede leerla. Cada clave viaja
solo a su propio servicio y nunca va en una dirección web; la lista de claves solo enseña el principio y el final de
cada una. Tu token de Hugging
Face nunca se manda a Spaces de terceros. Desinstalar no borra tus proyectos ni tus claves.

**¿Y si un servicio se queda sin saldo?**
«Comprobar conexiones» lo marca como «Sin saldo» y te dice dónde recargar (en Claude, OpenAI, Modal y algunos más,
solo se sabe al usarlos). Antes de un trabajo la app te avisa y sigue con otra opción: si tu IA de texto no tiene
saldo, usa otra conectada o la gratis sin clave; las imágenes pasan a la siguiente opción, y si la animación no puede,
la escena va con zoom suave. Si ya sabe que falta saldo, lo que solo se hace pagando (un video que habla, una canción)
ni empieza: te dice cómo arreglarlo y no se cobra nada. En **«Claves de IA»**, más abajo, el apartado
**«Actividad de la IA»** enseña cada uso de la IA y un cálculo por lo alto de lo gastado hoy y este mes.

**La app dice que mi clave no vale, pero sé que es buena.**
Lee el detalle del aviso. Si habla de un permiso («missing the permission…»), a la clave le falta un permiso:
ElevenLabs, por ejemplo, deja crear claves con permisos sueltos. En la web del servicio, edita la clave, dale acceso
completo y vuelve a conectarla o pulsa «Comprobar conexiones». Si el aviso es de conexión, revisa tu internet y
prueba otra vez.

**¿Dónde quedan mis videos?**
En **«🎬 Mis proyectos»**: elige uno y pulsa **«Abrir carpeta»**. Están en
`C:\Users\<tu usuario>\AppData\Local\Programs\Ráfaga Studio\datos\proyectos`.

**¿Funciona en Mac o Linux?**
Todavía no: por ahora es solo para Windows 10 y 11.

## 🎬 Hecho con Ráfaga Studio

| Personaje que habla (9:16) | Tráiler anime (16:9) | Movimiento real de IA (Wan 2.2) |
|---|---|---|
| <img src="ejemplos/manzana-habla.gif" width="170" alt="Una manzana animada que habla"> | <img src="ejemplos/leyenda-rafaga.gif" width="300" alt="Tráiler anime La leyenda de Ráfaga"> | <img src="ejemplos/leyenda-ia.gif" width="300" alt="La leyenda de Ráfaga animada con IA de video"> |
| [ver video](ejemplos/manzana-habla.mp4) · voz propia y labios sincronizados (Gemini Omni) | [ver video](ejemplos/leyenda-rafaga.mp4) · personajes originales | [ver video](ejemplos/leyenda-ia.mp4) · el viento, el pelo y la cámara se mueven, en tu nube Modal |

| Mascota en 4K (1:1) | Miniatura de YouTube (16:9) |
|---|---|
| <img src="assets/mascota.jpg" width="200" alt="Rafa, la mascota de Ráfaga Studio"> | <img src="ejemplos/miniatura-leyenda.jpg" width="320" alt="Miniatura de La leyenda de Ráfaga"> |

| Portada de álbum (1:1) | Flyer de evento (A4) | Logo |
|---|---|---|
| <img src="ejemplos/portada-alto-voltaje.jpg" width="240" alt="Portada de álbum de un artista de dembow ficticio"> | <img src="ejemplos/flyer-noche-neon.jpg" width="170" alt="Flyer de la fiesta Noche Neón"> | <img src="ejemplos/logo-barberia-el-rey.jpg" width="240" alt="Logo de Barbería El Rey"> |
| «Alto Voltaje», de un artista de dembow ficticio · neón oscuro | Flyer de fiesta con fecha, hora y lugar · neón oscuro | Emblema con corona de «Barbería El Rey» · render 3D |

| Miniatura de YouTube (16:9) | Estampado para camiseta | Anuncio de marca (4:5) |
|---|---|---|
| <img src="ejemplos/miniatura-capitulo-2.jpg" width="300" alt="Miniatura del capítulo 2 de La leyenda de Ráfaga"> | <img src="ejemplos/estampado-calavera-neon.jpg" width="240" alt="Estampado de calavera neón"> | <img src="ejemplos/anuncio-cafe-brisa-alta.jpg" width="200" alt="Anuncio de Café Brisa Alta"> |
| «La leyenda de Ráfaga», capítulo 2 · anime con brillo neón | Calavera neón para camiseta negra · neón oscuro | «Café Brisa Alta», el producto en primer plano · render 3D |

Los guiones y los diseños (en capas editables) los escribió Claude como Director. Las imágenes (FLUX), las voces, los
subtítulos, el movimiento y el montaje los hizo el software. El arte de los seis diseños lo dibujó Gemini (Nano Banana
en 2K, unos US$0,05 por imagen) y el estudio encajó los textos. Todo se vuelve a crear con `python ejemplos/crear.py` y
`python ejemplos/crear_disenos.py` (los pedidos, guiones y diseños están en [`ejemplos/ejemplos.json`](ejemplos/ejemplos.json)
y [`ejemplos/disenos.json`](ejemplos/disenos.json)). Las marcas y las personas son ficticias.

**Tal como salieron en una prueba real de cada herramienta:**

| Movimiento con IA, «Solo animar la imagen» (9:16) | Capítulo de dibujos animados (9:16) |
|---|---|
| <img src="ejemplos/baile-merengue.gif" width="170" alt="Una pareja ficticia hecha con IA bailando merengue en una calle con palmeras"> | <img src="ejemplos/rafa-y-la-ciudad.gif" width="170" alt="Rafa y la ciudad, dibujos animados hechos con Ráfaga Studio"> |
| [ver video](ejemplos/baile-merengue.mp4) · ella gira y la falda vuela | [ver video](ejemplos/rafa-y-la-ciudad.mp4) · dibujos fijos con zoom suave, cada personaje con su voz |

| Post de Instagram (1:1) | Los personajes |
|---|---|
| <img src="ejemplos/promo-barberia-el-rey.jpg" width="240" alt="Post de la promo de los martes de una barbería ficticia"> | <img src="ejemplos/personajes-rafa-y-la-ciudad.jpg" width="360" alt="Rafa, Yari y Don Tito, los personajes de la serie"> |
| La promo de los martes de «Barbería El Rey», pedida en una frase | Rafa, Yari y Don Tito: las láminas que el estudio usa de referencia en cada plano |

Del capítulo se quitaron dos de sus seis planos: uno tenía una falta en el guion y el otro se quedó sin dibujo cuando se
acabó el saldo gratis de Pollinations. El baile empezó como una imagen de otro video hecho en el estudio y lo animó
Wan 2.2 en tu propia nube Modal (unos US$0,30-0,60 de su crédito gratis del mes). Los personajes de la serie los
escribió Claude como Director; el guion lo hizo Groq, los dibujos Pollinations y las voces Edge, todo gratis. El post
lo maquetó Gemini (unos céntimos) sobre una foto gratis de Pollinations. Las marcas y las personas son ficticias.

## 🧰 Qué hace

| Pantalla | Qué hace |
|---|---|
| 🤖 Director IA | Le pides el trabajo por escrito **o con tu voz**, como a tu equipo («hazme un anuncio de mi barbería y un post»), y la IA usa todo el estudio: guion, imágenes, video, diseño, música y edición |
| ✨ Crear con IA | Guion con IA → imágenes → voz → animación → subtítulos tipo CapCut. Opcional: personajes que hablan con los labios sincronizados |
| 🎨 Diseño | Espacio de trabajo tipo Illustrator (herramientas en columna, zoom, alinear, propiedades y capas; texto, formas, fotos, 2.100+ iconos, emojis y 14 fuentes, también góticas) y una IA que primero entiende tu pedido (pregunta si duda, también con faltas), dibuja ilustraciones en vez de fotos de banco y hace anuncios, posts, miniaturas, flyers, logos y estampados para camisetas **en capas editables**, sin inventar precios ni contactos. Modos de fusión y ajustes de imagen como en Photoshop, quitar fondo, «Editar con IA» y exportar en 4K; PNG, JPG, PDF y SVG |
| 🐰 Dibujos animados | Tu serie capítulo por capítulo: la IA crea personajes originales (con su apariencia fija, su lámina y su voz) y escribe cada capítulo siguiendo la historia. Guion gráfico con cada plano, rehacer un solo plano y cuadros para retocar en OpenToonz, Pencil2D o Krita |
| ✂️ Editor de video | Línea de tiempo tipo CapCut: cortes, velocidad, transiciones, textos, stickers, música, voz con IA y subtítulos automáticos; exporta MP4 hasta 4K. **Grábate** hablando encima del video con tu cámara (o solo tu voz, o importa un video de tu cara): disposiciones de un clic (círculo en una esquina, pantalla completa o dividida), la música baja sola mientras hablas y los subtítulos te oyen. La cámara y el micro se quedan en tu PC y solo se encienden cuando tú lo pides |
| ⚡ Shorts mágicos | Pega un enlace; la IA elige los mejores momentos y los recorta en vertical con subtítulos |
| 🚀 Anuncios | Foto del producto → varias versiones de anuncio (pruebas A/B) con tu producto real |
| 🎵 Música | Letra y producción con IA en cualquier género (dembow, reggaetón, bachata…); video musical con ondas y letra karaoke |
| 🎙️ Cabina | Graba sobre la pista; afinación, cadena de voz por género, mezcla con sidechain y máster |
| 🔎 Nichos virales | Vistas por día reales de YouTube + investigación web en vivo (con Claude) → nichos con ideas listas |
| 📅 Publicar | Programa tus videos en YouTube con tu propia app de Google: YouTube los publica a la hora elegida, aunque apagues el PC |
| 🔌 MCP | Claude (u otro agente) puede usar todo el estudio desde el chat |

### El Director y el asistente de voz

El Director es la IA que maneja el estudio entero. Tú eres la marca o el creador: pides el trabajo y él decide qué
herramientas usar, las usa una tras otra y te entrega los videos, diseños o canciones. Trabaja como un estudio con
departamentos (guion y video, diseño, música y voz, dibujos animados, anuncios, edición, publicación y nichos), cada
uno con sus reglas de calidad. Funciona con cualquier IA de texto conectada (también la gratis sin clave) y se detiene
tras 6 pasos para no gastar de más. Antes de algo que cuesta dinero o publica en tu canal te dice el costo y te
pregunta (también con la voz: contesta «sí» o «no»), y recuerda tus gustos por departamento: los ves y los borras en
«Memoria del estudio».

Pulsa **Hablar** o **Ctrl+Espacio** y pídeselo con la voz: escucha solo mientras está activo, se para cuando terminas
de hablar y te contesta en voz alta. Mientras te escucha, piensa o habla, una luz de colores recorre el borde de la
ventana y se ilumina la página que está usando. Tu voz se entiende en tu PC con Whisper y la respuesta usa las voces
gratis de Edge: no hace falta ElevenLabs ni ningún servicio de pago.

## 🔑 Todos los servicios (trae tus propias claves)

**Lo gratis va primero** en imágenes y video: rotan entre nubes (cuota diaria gratis → este PC → créditos → pago), para
que puedas crear todos los días sin gastar. Para el texto y la transcripción eliges tú el proveedor. Kling y Seedance
se conectan con su propio botón «Conectar» en «Claves de IA».

| Tarea | Gratis | Con crédito o de pago |
|---|---|---|
| Texto / guiones | Groq, Gemini, Pollinations (sin clave) | Claude, OpenAI, OpenRouter, xAI, DeepSeek |
| Imágenes | Cloudflare Workers AI (~100/día), Pollinations, FLUX en Hugging Face (sin clave, unas pocas al día) | OpenAI, Replicate, Gemini Nano Banana (solo si lo eliges: ~US$0,07 por imagen; mantiene iguales personajes y productos) |
| Video IA (imagen → video) | Hugging Face ZeroGPU (Wan 2.2) | Modal (US$30 gratis al mes con tarjeta), Pollinations, Kling y Seedance (solo si los eliges: ~US$0,02-0,24 por segundo; antes de cada trabajo la app te dice lo más que puede costar, con un tope de 15 clips de pago por trabajo) |
| Video animado con voz (los personajes hablan, labios sincronizados) | — | Gemini Omni (~US$0,10 por segundo; la app usa el modelo más nuevo de precio conocido de tu clave), o Kling o Seedance si los eliges en «Escenas que hablan». Crear te dice el costo antes, el Director te pregunta antes de usarlo y un agente MCP solo lo consigue con tu «Sí» en una ventana de Ráfaga Studio que el agente no puede leer ni contestar |
| Voz | Voces de Edge | ElevenLabs |
| Transcripción | Este PC (Whisper), Groq | OpenAI |
| Separar voz y pista | Este PC (Demucs): tu música no sale de tu PC | — |
| Música | — | ElevenLabs Music, Gemini Lyria |

## 🔌 Úsalo desde Claude (MCP)

Abre **«🔌 Conexión MCP»** en la app y pulsa conectar: Ráfaga Studio se registra en Claude Code y Claude Desktop.
Luego pídeselo a Claude: *«Hazme un video vertical de 30 segundos sobre tres lugares de República Dominicana»*. El
servidor MCP trae 17 herramientas, entre ellas `crear_video`, `sacar_shorts`, `crear_anuncios`, `crear_cancion`,
`crear_video_musical`, `crear_diseno`, `editar_video`, `crear_serie`, `crear_episodio`, `investigar_nichos` y
`programar_publicacion`. Son las mismas que usa el Director dentro de la app.

## 🔒 Seguridad y privacidad

**Se instala y trabaja en tu PC**: sin servidores nuestros, sin cuentas, sin analíticas ni telemetría. Tus proyectos y
claves se guardan en tu PC (carpeta `datos`). Las funciones de IA usan servicios de internet: tus pedidos, textos e
imágenes van directo al servicio que hace el trabajo, también los gratis sin clave (Pollinations, un Space público de
Hugging Face, las voces de Microsoft). El detalle, función por función, está en el [Aviso de privacidad](PRIVACIDAD.md).

- **Tus claves** se guardan cifradas con tu cuenta de Windows (DPAPI) en `datos/claves.json`: solo tu usuario en tu
  PC puede leerlas. Nunca van en direcciones web ni se suben a GitHub (`datos/` está en `.gitignore`).
- **Tu token de Hugging Face nunca se envía a Spaces de terceros**: se usan sin token, con la cuota anónima.
- **El servidor MCP solo acepta imágenes y audios de tu disco** y enlaces de sitios conocidos, así una web
  maliciosa no puede pedirle a Claude que saque archivos privados ni que ataque tu red.
- **Qué sale de tu PC:** la cabina (voz, mezcla, máster), la separación de voz y lo que le dices al Director con el
  micrófono se procesan siempre en tu PC. Los guiones, las imágenes y la animación usan los servicios que conectes; en
  el modo gratis sin clave, Pollinations (pedido como privado) y Spaces públicos de Hugging Face, que reciben lo que
  se les manda. Si no quieres que tus imágenes vayan a un Space público, pon «Animar escenas con IA de video» en «No
  usar» en «Claves de IA».
- ¿Encontraste un problema de seguridad? Sigue [SECURITY.md](SECURITY.md) en lugar de abrir un *issue* público.

### 🛡️ Ráfaga Guardia

El vigilante de la app, al final del menú (su escudo se pone verde, ámbar o rojo). Apunta en tu PC
(`datos/guardia.json`) lo que la app frena: rutas de red, enlaces a tu red local, archivos que fingen ser otra cosa,
agentes MCP que insisten después de tu «No», claves de otro servicio, claves que Windows no puede descifrar o que
cambió otro programa. Comprueba que el código de la app es el que instalaste (el instalador lleva la huella de cada
archivo) y, si el código cambió o un agente te insiste 3 veces en 10 minutos, **bloquea** el video, las imágenes, la
música y la voz de pago, publicar, la memoria y el MCP hasta que lo desbloquees tú, en su página. Los eventos graves
salen como notificación de Windows. Las reglas deciden; la IA solo te explica un evento si pulsas «Explicar con IA».
Protege la app y lo que guarda (tus claves, tu dinero y tus datos), **no el PC entero**: no es un antivirus. Límites en
[SECURITY.md](SECURITY.md).

## 🧑‍💻 Para programadores

**Desde el código:**

```bat
git clone https://github.com/santo29/rafaga-studio.git
cd rafaga-studio
"Ráfaga Studio.bat"
```

El `.bat` crea el entorno, instala las versiones exactas ya probadas (`requirements.lock`, con el hash de cada
archivo) y abre la app. Requiere Python 3.14; [Node.js](https://nodejs.org) se recomienda para descargar de YouTube.
Para fabricar el instalador: `ISCC instalador\rafaga.iss` ([Inno Setup](https://jrsoftware.org/isinfo.php) 7). Las
pruebas corren sin internet ni claves: `python -m pruebas`.

**Solo el motor, desde Python:**

```python
from motor import shorts, cabina
shorts.generar("https://youtu.be/…", formato="9:16", cantidad=3)
cabina.sesion("beat.mp3", "mi_voz.wav", estilo="Dembow / urbano (seco y al frente)")
```

## 📄 Open core: qué es abierto

| Parte | Licencia |
|---|---|
| `motor/` — el motor sin interfaz, se usa como librería | **MIT** (abierto) |
| `idiomas/` — las traducciones que usa el motor | **MIT** (abierto) |
| `mcp_server.py` — para que Claude u otro agente use el estudio | **MIT** (abierto) |
| `modal_app.py` — video IA en tu propia nube de Modal | **MIT** (abierto) |
| `pruebas/__main__.py` y `pruebas/seguridad.py` — pruebas sin internet ni claves (`python -m pruebas`) | **MIT** (abierto) |
| `ejemplos/` — los videos de ejemplo y cómo se hicieron (`python ejemplos/crear.py`) | **MIT** (abierto) |
| `assets/iconos` (Lucide) y `assets/fuentes` (Google Fonts), ver `assets/LEEME.md` | ISC (iconos) y OFL (fuentes) |
| `assets/icono.*`, `assets/portada-github.png` y `assets/mascota.jpg` — logo, portada y mascota | Marca Ráfaga Studio™, todos los derechos reservados |
| Las demás pruebas (`pruebas/*.py`), `pruebas/real.py`, `instalador/actualizar_lock.py` e `instalador/` | Parte de la app, todos los derechos reservados |
| `app.py` y `ui/` — la app de escritorio | Código visible, todos los derechos reservados (Ráfaga Studio Pro): no es open source |

Hecho con: FFmpeg, faster-whisper, yt-dlp, Pedalboard (Spotify), Demucs (Meta), Matchering, librosa, PSOLA/Praat,
Wan 2.2, FLUX, edge-tts, Lucide, Google Fonts.

## 🤝 Contribuir

¿Quieres ayudar? Lee [CONTRIBUTING.md](CONTRIBUTING.md): abre un *issue* con ideas o errores, o manda un *pull
request*. Lo más útil ahora: más proveedores gratis en `motor/nubes.py`, nuevos estilos de voz en `motor/cabina.py`,
géneros en `motor/musica.py` y traducciones en `idiomas/`.

Si Ráfaga Studio te sirve, **dale una ⭐** y compártelo con un creador que no sepa programar: así lo encuentran más
personas.

**Usa contenido propio o con permiso.** Las redes no pagan por contenido ajeno reutilizado. Marca como «hecho con IA»
el contenido realista generado o alterado con IA: YouTube, TikTok y Meta lo exigen.

## 💜 Conoce a Rafa

<img src="assets/mascota.jpg" width="360" align="right" alt="Rafa, la mascota de Ráfaga Studio">

Rafa es la mascota del estudio y se hizo **con el diseñador de Ráfaga Studio**: Claude escribió el diseño como Director y el estudio lo dibujó en 4K.

Hecho por un dominicano con Dios y su mejor amigo, Claude. Si te ayuda a crear, una ⭐ lo ayuda a llegar a más creadores.

<br clear="right">

## Legal y marca

- [Aviso de privacidad](PRIVACIDAD.md) · [Términos de uso](TERMINOS.md) · [Avisos de terceros](AVISOS_DE_TERCEROS.md)
  · [Licencia](LICENSE)
- **Ráfaga Studio™**: el nombre, el logo y la identidad visual son marcas de **Santo Montilla**. La licencia MIT del
  motor no da permiso para usar la marca.
- © 2026 Santo Montilla. La app de escritorio (`app.py` y `ui/`) tiene todos los derechos reservados.
