# ⚡ Ráfaga Studio

[**🇬🇧 Read in English**](README.md) · [**⬇ Descargar para Windows**](https://github.com/santo29/rafaga-studio/releases/latest)

**Estudio creativo con IA para escritorio (Windows):** crea videos desde un prompt, saca shorts virales de videos largos,
hace anuncios realistas con la foto de tu producto, compone canciones (dembow, reggaetón, bachata y más), graba tu voz
y la mezcla y masteriza como un ingeniero, investiga nichos virales y hace el video musical. Todo con un clic.

> *AI creative studio for the desktop: prompt-to-video, long-video-to-shorts, realistic product ads, AI songs,
> an AI recording booth (tuning, mixing, mastering), viral niche research and music videos. Bring your own keys.*

**Idiomas:** español, English, Português y Français. En «Automático» la app usa el idioma de tu PC y, si tu Windows
está en inglés (como vienen muchos de fábrica), el de tu país. Se cambia abajo del menú lateral.

## Conoce Ráfaga Studio en un minuto

<a href="ejemplos/presentacion-app.mp4"><img src="ejemplos/presentacion-app.gif" width="560" alt="Video de presentación de Ráfaga Studio"></a>

[▶ Ver el video completo](ejemplos/presentacion-app.mp4). Lo montó el propio editor de Ráfaga Studio: capturas reales de
la app, el anime con movimiento de IA, transiciones, Brillo Ráfaga, subtítulos Karaoke Ráfaga y la voz de Edge. El guion
lo escribió Claude como Director.

## Hecho con Ráfaga Studio

| Short viral (9:16) | Anuncio (9:16) | Tráiler anime (16:9) |
|---|---|---|
| <img src="ejemplos/lugares-rd.gif" width="200" alt="3 lugares de RD que parecen de otro planeta"> | <img src="ejemplos/anuncio-cafe.gif" width="200" alt="Anuncio de Café Brisa Alta"> | <img src="ejemplos/leyenda-rafaga.gif" width="320" alt="Tráiler anime La leyenda de Ráfaga"> |
| **3 lugares de RD que parecen de otro planeta** · [ver video](ejemplos/lugares-rd.mp4) | **Café Brisa Alta** · [ver video](ejemplos/anuncio-cafe.mp4) | **La leyenda de Ráfaga** · [ver video](ejemplos/leyenda-rafaga.mp4) |

**Video animado con voz** (Gemini Omni: la manzana habla con su propia voz y los labios sincronizados; se pidió en una frase y el estudio hizo el guion, las escenas y los subtítulos):

<img src="ejemplos/manzana-habla.gif" width="200" alt="Una manzana animada que habla"> · [ver video](ejemplos/manzana-habla.mp4)

**Con movimiento real de IA** (Wan 2.2 en tu propia nube Modal: el viento, el pelo, la cámara y las chispas se mueven):

<img src="ejemplos/leyenda-ia.gif" width="420" alt="La leyenda de Ráfaga animada con IA de video"> · [ver video](ejemplos/leyenda-ia.mp4)

| Presentación (16:9) | Post de marca (4:5) | Miniatura de YouTube (16:9) |
|---|---|---|
| <img src="ejemplos/presentacion-rafaga.jpg" width="320" alt="Portada de presentación de Ráfaga Studio"> | <img src="ejemplos/post-cafe.jpg" width="200" alt="Post de Café Brisa Alta"> | <img src="ejemplos/miniatura-leyenda.jpg" width="320" alt="Miniatura de La leyenda de Ráfaga"> |

Los guiones y los diseños (en capas editables) los escribió Claude como Director. Las imágenes (FLUX), las voces, los subtítulos, el movimiento y el
montaje los hizo el software. Se vuelven a crear con `python ejemplos/crear.py` y `python ejemplos/crear_disenos.py` (los pedidos, guiones y diseños están en
`ejemplos/ejemplos.json` y `ejemplos/disenos.json`).

## Qué hace

| Pantalla | Qué hace |
|---|---|
| 🤖 Director IA | Le pides el trabajo por escrito **o con tu voz**, como a tu equipo («hazme un anuncio de mi barbería y un post»), y la IA usa todo el estudio: guion, imágenes, video, diseño, música y edición |
| ✨ Crear con IA | Guion con IA → imágenes → voz → animación → subtítulos tipo CapCut |
| 🎨 Diseño | Espacio de trabajo tipo Illustrator (herramientas en columna, zoom, alinear, propiedades y capas; texto, formas, fotos, 2.100+ iconos, emojis y 14 fuentes, también góticas) y una IA que primero entiende tu pedido (pregunta si duda, también con faltas), dibuja ilustraciones en vez de fotos de banco y hace anuncios, posts, miniaturas, flyers, logos y estampados para camisetas **en capas editables**, sin inventar precios ni contactos. Modos de fusión y ajustes de imagen como en Photoshop, quitar fondo, «Editar con IA» y exportar en 4K; PNG, JPG, PDF y SVG |
| 🐰 Dibujos animados | Tu serie de dibujos animados capítulo por capítulo: la IA crea personajes originales (con su apariencia fija, su lámina y su voz) y escribe cada capítulo siguiendo la historia; cada plano sale con imagen, movimiento y la voz de quien habla. Guion gráfico con cada plano, rehacer un solo plano y cuadros para retocar en OpenToonz, Pencil2D o Krita |
| ✂️ Editor de video | Línea de tiempo tipo CapCut: cortes, velocidad, transiciones, textos, stickers, música, voz con IA y subtítulos automáticos; exporta MP4 |
| ⚡ Shorts mágicos | Pega un enlace; la IA elige los mejores momentos y los recorta en vertical con subtítulos |
| 🚀 Anuncios | Foto del producto → varias versiones de anuncio (pruebas A/B) con tu producto real |
| 🎵 Música | Letra y producción con IA en cualquier género; video musical con ondas y letra karaoke |
| 🎙️ Cabina | Graba sobre la pista; afinación, cadena de voz por género, mezcla con sidechain y master |
| 🔎 Nichos virales | Vistas por día reales de YouTube + investigación web en vivo (con Claude) → nichos con ideas listas |
| 📅 Publicar | Programa tus videos en YouTube con tu propia app de Google: YouTube los publica a la hora elegida, aunque apagues el PC |
| 🔌 MCP | Claude (u otro agente) puede usar todo el estudio desde el chat |

## El Director y el asistente de voz

El Director es la IA que maneja el estudio entero. Tú eres la marca o el creador: pides el trabajo y él decide qué
herramientas usar, las usa una tras otra y te entrega los videos, diseños o canciones. Usa las mismas herramientas que
el servidor MCP, así que también lo puedes dirigir desde Claude. Funciona con cualquier IA de texto conectada (también
la gratis sin clave) y se detiene tras 6 pasos para no gastar de más. Trabaja como un estudio con departamentos
(guion y video, diseño, música y voz, dibujos animados, anuncios, edición, publicación y nichos), cada uno con sus
reglas de calidad. Antes de algo que cuesta dinero o publica en tu canal te dice el costo y te pregunta (también con la
voz: contesta «sí» o «no»), y recuerda tus gustos por departamento: los ves y los borras en «Memoria del estudio».

Pulsa **Hablar** o **Ctrl+Espacio** y pídeselo con la voz: escucha solo mientras está activo, se para solo cuando
terminas de hablar y te contesta en voz alta. Mientras te escucha, piensa o habla, una luz de colores recorre el borde
de la ventana y se ilumina la página que está usando. Tu voz se entiende en tu PC con Whisper y la respuesta usa las
voces gratis de Edge: no hace falta ElevenLabs ni ningún servicio de pago.

## Trae tus propias claves (BYOK)

Pega cualquier clave y Ráfaga Studio detecta el proveedor y elige el modelo. **Lo gratis va primero** en imágenes y
video: rotan entre nubes (cuota diaria gratis → este PC → créditos → pago), para que puedas crear todos los días sin
gastar. Para el texto y la transcripción eliges tú el proveedor.

| Tarea | Gratis | Con crédito o de pago |
|---|---|---|
| Texto / guiones | Groq, Gemini, Pollinations (sin clave) | Claude, OpenAI, OpenRouter, xAI, DeepSeek |
| Imágenes | Cloudflare Workers AI (~100/día), Pollinations, FLUX en Hugging Face (sin clave, unas pocas al día) | OpenAI, Replicate, Gemini Nano Banana (solo si lo eliges: ~US$0,07 por imagen; mantiene iguales personajes y productos) |
| Video IA (imagen → video) | Hugging Face ZeroGPU (Wan 2.2) | Modal ($30 gratis/mes), Pollinations |
| Video animado con voz (los personajes hablan, labios sincronizados) | — | Gemini Omni (~US$0,10 por segundo; la app usa el modelo más nuevo de precio conocido de tu clave, Crear te dice el costo antes y el Director te pregunta antes de usarlo) |
| Voz | Voces de Edge | ElevenLabs |
| Transcripción | Este PC (Whisper), Groq | OpenAI |
| Separar voz y pista | Este PC (Demucs): tu música no sale de tu PC | — |
| Música | — | ElevenLabs Music, Gemini Lyria |

## Instalar

**Con el instalador (recomendado):** baja el `.exe` de `RafagaStudio-Setup` en
[Versiones](https://github.com/santo29/rafaga-studio/releases/latest) y ábrelo. No pide permisos de administrador. El
instalador baja el Python portátil oficial y las librerías de IA (unos 1,5 GB) y comprueba la huella SHA-256 de cada
archivo.

**Desde el código:**

```bat
git clone https://github.com/santo29/rafaga-studio.git
cd rafaga-studio
"Ráfaga Studio.bat"
```

El `.bat` crea el entorno, instala las versiones exactas ya probadas (`requirements.lock`, con el hash de cada
archivo) y abre la app. Requiere Python 3.14; [Node.js](https://nodejs.org) se recomienda para descargar de YouTube.
Para fabricar el instalador: `ISCC instalador\rafaga.iss` ([Inno Setup](https://jrsoftware.org/isinfo.php) 7).

## Seguridad y privacidad

**Se instala y trabaja en tu PC**: sin servidores nuestros, sin cuentas, sin analíticas ni telemetría. Tus proyectos y
claves se guardan en tu PC (carpeta `datos`). Las funciones de IA usan servicios de internet: tus pedidos, textos e
imágenes van directo al servicio que hace el trabajo, también los gratis sin clave (Pollinations, un Space público de
Hugging Face, las voces de Microsoft). El detalle completo, función por función, está en el
[Aviso de privacidad](PRIVACIDAD.md).

- **Tus claves** se guardan cifradas con tu cuenta de Windows (DPAPI) en `datos/claves.json`: solo tu usuario en tu
  PC puede leerlas. Nunca van en direcciones web ni se suben a GitHub (`datos/` está en `.gitignore`).
- **Tu token de Hugging Face nunca se envía a Spaces de terceros**: se usan sin token, con la cuota anónima.
- **El servidor MCP solo acepta imágenes y audios de tu disco** y enlaces de sitios conocidos, así una web
  maliciosa no puede pedirle a Claude que saque archivos privados ni que ataque tu red.
- **Qué sale de tu PC:** la cabina (voz, mezcla, master), la separación de voz y lo que le dices al Director con el
  micrófono se procesan siempre en tu PC (tu voz no sale de él). Los guiones, las
  imágenes y la animación usan los servicios que conectes; en el modo gratis sin clave, Pollinations (pedido como
  privado) y Spaces públicos de Hugging Face, que reciben lo que se les manda.
- ¿Encontraste un problema de seguridad? Sigue [SECURITY.md](SECURITY.md) en lugar de abrir un *issue* público.

Solo el motor, desde Python:

```python
from motor import shorts, cabina
shorts.generar("https://youtu.be/…", formato="9:16", cantidad=3)
cabina.sesion("beat.mp3", "mi_voz.wav", estilo="Dembow / urbano (seco y al frente)")
```

## Open core: qué es abierto

| Parte | Licencia |
|---|---|
| `motor/` — el motor sin interfaz, se usa como librería | **MIT** (abierto) |
| `idiomas/` — las traducciones que usa el motor | **MIT** (abierto) |
| `mcp_server.py` — para que Claude u otro agente use el estudio | **MIT** (abierto) |
| `modal_app.py` — video IA en tu propia nube de Modal | **MIT** (abierto) |
| `pruebas/__main__.py` y `pruebas/seguridad.py` — pruebas sin internet ni claves (`python -m pruebas`) | **MIT** (abierto) |
| `ejemplos/` — los videos de ejemplo y cómo se hicieron (`python ejemplos/crear.py`) | **MIT** (abierto) |
| `assets/iconos` (Lucide) y `assets/fuentes` (Google Fonts), ver `assets/LEEME.md` | ISC (iconos) y OFL (fuentes) |
| `assets/icono.*` y `assets/portada-github.png` — logo y portada | Marca Ráfaga Studio™, todos los derechos reservados |
| Las demás pruebas (`pruebas/*.py`), `pruebas/real.py`, `instalador/actualizar_lock.py` e `instalador/` | Parte de la app, todos los derechos reservados |
| `app.py` y `ui/` — la app de escritorio | Código visible, todos los derechos reservados (Ráfaga Studio Pro): no es open source |

¿Quieres ayudar? Lee [CONTRIBUTING.md](CONTRIBUTING.md): abre un *issue* con ideas o errores, o manda un *pull
request*. Si Ráfaga Studio te sirve, **dale una ⭐**: ayuda a que otros creadores lo encuentren. Lo más útil ahora: más
proveedores gratis en `motor/nubes.py`, nuevos estilos de voz en `motor/cabina.py` y géneros en `motor/musica.py`.

Hecho con: FFmpeg, faster-whisper, yt-dlp, Pedalboard (Spotify), Demucs (Meta), Matchering, librosa, PSOLA/Praat,
Wan 2.2, FLUX, edge-tts, Lucide, Google Fonts.

**Usa contenido propio o con permiso.** Las redes no pagan por contenido ajeno reutilizado. Marca como «hecho con IA»
el contenido realista generado o alterado con IA: YouTube, TikTok y Meta lo exigen.

## Legal y marca

- [Aviso de privacidad](PRIVACIDAD.md) · [Términos de uso](TERMINOS.md) · [Avisos de terceros](AVISOS_DE_TERCEROS.md)
  · [Licencia](LICENSE)
- **Ráfaga Studio™**: el nombre, el logo y la identidad visual son marcas de **Santo Montilla**. La licencia MIT del
  motor no da permiso para usar la marca.
- © 2026 Santo Montilla. La app de escritorio (`app.py` y `ui/`) tiene todos los derechos reservados.
