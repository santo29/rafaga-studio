# ⚡ Ráfaga Studio

**Estudio creativo con IA para escritorio (Windows):** crea videos desde un prompt, saca shorts virales de videos largos,
hace anuncios realistas con la foto de tu producto, compone canciones (dembow, reggaetón, bachata y más), graba tu voz
y la mezcla y masteriza como un ingeniero, investiga nichos virales y hace el video musical. Todo con un clic.

> *AI creative studio for the desktop: prompt-to-video, long-video-to-shorts, realistic product ads, AI songs,
> an AI recording booth (tuning, mixing, mastering), viral niche research and music videos. Bring your own keys.*

**Idiomas:** español, English, Português y Français. En «Automático» la app usa el idioma de tu PC y, si tu Windows
está en inglés (como vienen muchos de fábrica), el de tu país. Se cambia abajo del menú lateral.

## Qué hace

| Pantalla | Qué hace |
|---|---|
| ✨ Crear con IA | Guion con IA → imágenes → voz → animación → subtítulos tipo CapCut |
| ⚡ Shorts mágicos | Pega un enlace; la IA elige los mejores momentos y los recorta en vertical con subtítulos |
| 🚀 Anuncios | Foto del producto → varias versiones de anuncio (pruebas A/B) con tu producto real |
| 🎵 Música | Letra y producción con IA en cualquier género; video musical con ondas y letra karaoke |
| 🎨 Diseño | Editor por capas tipo Canva (texto, formas, fotos, 2.100+ iconos, emojis, 8 fuentes) y una IA que diseña anuncios, posts, miniaturas, flyers y logos **en capas editables** con tu marca; exporta PNG, JPG, PDF y SVG |
| 🎙️ Cabina | Graba sobre la pista; afinación, cadena de voz por género, mezcla con sidechain y master |
| 🔎 Nichos virales | Vistas por día reales de YouTube + investigación web en vivo → nichos con ideas listas |
| 🔌 MCP | Claude (u otro agente) puede usar todo el estudio desde el chat |

## Trae tus propias claves (BYOK)

Pega cualquier clave y Ráfaga Studio detecta el proveedor y elige el modelo. **Lo gratis va primero**: cada tarea rota
entre nubes (cuota diaria gratis → este PC → créditos → pago), para que puedas crear todos los días sin gastar.

| Tarea | Gratis | Con crédito o de pago |
|---|---|---|
| Texto / guiones | Groq, Gemini | Claude, OpenAI, OpenRouter, xAI, DeepSeek |
| Imágenes | Cloudflare Workers AI (~100/día), Pollinations | OpenAI, Replicate |
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
- **Qué sale de tu PC:** la cabina (voz, mezcla, master) y la separación de voz se hacen en tu PC. Los guiones, las
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
| `assets/` — iconos Lucide y fuentes de Google Fonts (ver `assets/LEEME.md`) | ISC (iconos) y OFL (fuentes) |
| `app.py` y `ui/` — la app de escritorio | Privado (Ráfaga Studio Pro) |

¿Quieres ayudar? Abre un *issue* con ideas o errores, o manda un *pull request*. Lo más útil ahora mismo: más
proveedores gratis en `motor/nubes.py`, nuevos estilos de voz en `motor/cabina.py` y géneros en `motor/musica.py`.

Hecho con: FFmpeg, faster-whisper, yt-dlp, Pedalboard (Spotify), Demucs (Meta), Matchering, librosa, PSOLA/Praat,
Wan 2.2, FLUX, edge-tts, Lucide, Google Fonts.

**Usa contenido propio o con permiso.** Las redes no pagan por contenido ajeno reutilizado.
