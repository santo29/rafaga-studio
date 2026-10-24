# ⚡ Ráfaga Studio

**Estudio creativo con IA para escritorio (Windows):** crea videos desde un prompt, saca shorts virales de videos largos,
hace anuncios realistas con la foto de tu producto, compone canciones (dembow, reggaetón, bachata y más), graba tu voz
y la mezcla y masteriza como un ingeniero, investiga nichos virales y hace el video musical. Todo con un clic.

> *AI creative studio for the desktop: prompt-to-video, long-video-to-shorts, realistic product ads, AI songs,
> an AI recording booth (tuning, mixing, mastering), viral niche research and music videos. Bring your own keys.*

**Idiomas:** español, English, Português y Français. En «Automático» la app usa el idioma de tu PC y, si tu Windows
está en inglés (como vienen muchos de fábrica), el de tu país. Se cambia abajo del menú lateral.

## Hecho con Ráfaga Studio

| Short viral (9:16) | Anuncio (9:16) | Tráiler anime (16:9) |
|---|---|---|
| <img src="ejemplos/lugares-rd.gif" width="200" alt="3 lugares de RD que parecen de otro planeta"> | <img src="ejemplos/anuncio-cafe.gif" width="200" alt="Anuncio de Café Brisa Alta"> | <img src="ejemplos/leyenda-rafaga.gif" width="320" alt="Tráiler anime La leyenda de Ráfaga"> |
| **3 lugares de RD que parecen de otro planeta** · [ver video](ejemplos/lugares-rd.mp4) | **Café Brisa Alta** · [ver video](ejemplos/anuncio-cafe.mp4) | **La leyenda de Ráfaga** · [ver video](ejemplos/leyenda-rafaga.mp4) |

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
| ⚡ Shorts mágicos | Pega un enlace; la IA elige los mejores momentos y los recorta en vertical con subtítulos |
| 🚀 Anuncios | Foto del producto → varias versiones de anuncio (pruebas A/B) con tu producto real |
| 🎵 Música | Letra y producción con IA en cualquier género; video musical con ondas y letra karaoke |
| 🎨 Diseño | Editor por capas tipo Canva (texto, formas, fotos, 2.100+ iconos, emojis, 8 fuentes) y una IA que diseña anuncios, posts, miniaturas, flyers y logos **en capas editables** con tu marca; exporta PNG, JPG, PDF y SVG |
| ✂️ Editor de video | Línea de tiempo tipo CapCut: cortes, velocidad, transiciones, textos, stickers, música, voz con IA y subtítulos automáticos; exporta MP4 |
| 🎞️ Serie animada | Tu serie de dibujos animados capítulo por capítulo: la IA crea personajes originales (con su apariencia fija, su lámina y su voz) y escribe cada capítulo siguiendo la historia; cada plano sale con imagen, movimiento y la voz de quien habla. Los cuadros se exportan para retocarlos en OpenToonz, Pencil2D o Krita |
| 🎙️ Cabina | Graba sobre la pista; afinación, cadena de voz por género, mezcla con sidechain y master |
| 🔎 Nichos virales | Vistas por día reales de YouTube + investigación web en vivo → nichos con ideas listas |
| 🔌 MCP | Claude (u otro agente) puede usar todo el estudio desde el chat |

## El Director y el asistente de voz

El Director es la IA que maneja el estudio entero. Tú eres la marca o el creador: pides el trabajo y él decide qué
herramientas usar, las usa una tras otra y te entrega los videos, diseños o canciones. Usa las mismas herramientas que
el servidor MCP, así que también lo puedes dirigir desde Claude. Funciona con cualquier IA de texto conectada (también
la gratis sin clave) y se detiene tras 6 pasos para no gastar de más.

Pulsa **Hablar** o **Ctrl+Espacio** y pídeselo con la voz: escucha solo mientras está activo, se para solo cuando
terminas de hablar y te contesta en voz alta. Mientras te escucha, piensa o habla, una luz de colores recorre el borde
de la ventana y se ilumina la página que está usando. Tu voz se entiende en tu PC con Whisper y la respuesta usa las
voces gratis de Edge: no hace falta ElevenLabs ni ningún servicio de pago.

## Trae tus propias claves (BYOK)

Pega cualquier clave y Ráfaga Studio detecta el proveedor y elige el modelo. **Lo gratis va primero**: cada tarea rota
entre nubes (cuota diaria gratis → este PC → créditos → pago), para que puedas crear todos los días sin gastar.

| Tarea | Gratis | Con crédito o de pago |
|---|---|---|
| Texto / guiones | Groq, Gemini | Claude, OpenAI, OpenRouter, xAI, DeepSeek |
| Imágenes | Cloudflare Workers AI (~100/día), Pollinations, FLUX en Hugging Face (sin clave, unas pocas al día) | OpenAI, Replicate |
| Video IA (imagen → video) | Hugging Face ZeroGPU (Wan 2.2) | Modal ($30 gratis/mes), Pollinations |
| Voz | Voces de Edge | ElevenLabs |
| Transcripción | Este PC (Whisper), Groq | OpenAI |
| Separar voz y pista | Este PC (Demucs): tu música no sale de tu PC | — |
| Música | — | ElevenLabs Music, Gemini Lyria |

## Instalar

```bat
git clone <este repositorio>
cd "Ráfaga Studio"
"Ráfaga Studio.bat"
```

El `.bat` crea el entorno, instala las versiones exactas ya probadas (`requirements.lock`, con el hash de cada
archivo) y abre la app. Requiere
Python 3.13+ y Node.js (para descargar de YouTube).

## Seguridad y privacidad

- **Tus claves** se guardan cifradas con tu cuenta de Windows (DPAPI) en `datos/claves.json`: solo tu usuario en tu
  PC puede leerlas. Nunca van en direcciones web ni se suben a GitHub (`datos/` está en `.gitignore`).
- **Tu token de Hugging Face nunca se envía a Spaces de terceros**: se usan sin token, con la cuota anónima.
- **El servidor MCP solo acepta imágenes y audios de tu disco** y enlaces de sitios conocidos, así una web
  maliciosa no puede pedirle a Claude que saque archivos privados ni que ataque tu red.
- **Qué sale de tu PC:** la cabina (voz, mezcla, master), la separación de voz y lo que le dices al Director con el
  micrófono se procesan siempre en tu PC (tu voz no sale de él). Los guiones, las
  imágenes y la animación usan los servicios que conectes; en el modo gratis sin clave, Pollinations (pedido como
  privado) y Spaces públicos de Hugging Face, que reciben lo que se les manda.
- ¿Encontraste un problema de seguridad? Escríbelo en privado a los responsables en lugar de abrir un *issue* público.

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
| `mcp_server.py` — para que Claude u otro agente use el estudio | **MIT** (abierto) |
| `modal_app.py` — video IA en tu propia nube de Modal | **MIT** (abierto) |
| `pruebas.py` — pruebas sin internet ni claves (`python pruebas.py`) | **MIT** (abierto) |
| `ejemplos/` — los videos de ejemplo y cómo se hicieron (`python ejemplos/crear.py`) | **MIT** (abierto) |
| `assets/` — iconos Lucide y fuentes de Google Fonts (ver `assets/LEEME.md`) | ISC (iconos) y OFL (fuentes) |
| `app.py` y `ui/` — la app de escritorio | Privado (Ráfaga Studio Pro) |

¿Quieres ayudar? Abre un *issue* con ideas o errores, o manda un *pull request*. Lo más útil ahora mismo: más
proveedores gratis en `motor/nubes.py`, nuevos estilos de voz en `motor/cabina.py` y géneros en `motor/musica.py`.

Hecho con: FFmpeg, faster-whisper, yt-dlp, Pedalboard (Spotify), Demucs (Meta), Matchering, librosa, PSOLA/Praat,
Wan 2.2, FLUX, edge-tts, Lucide, Google Fonts.

**Usa contenido propio o con permiso.** Las redes no pagan por contenido ajeno reutilizado.
