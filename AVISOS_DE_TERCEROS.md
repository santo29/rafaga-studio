# Avisos de terceros

Ráfaga Studio se apoya en software libre, modelos abiertos y servicios de terceros. Cada uno conserva su licencia y sus
condiciones. Este archivo las reúne.

## Importante: librerías GPL

Cuatro librerías tienen licencia **GPLv3** (praat-parselmouth, GPLv3 o posterior). Se importan solo en
`motor/cabina.py` y las usan la **Cabina de grabación** y la herramienta «producir canción» del Director y del
servidor MCP:

- **pedalboard** (Spotify), la cadena de voz;
- **matchering**, el máster con referencia;
- **psola** y **praat-parselmouth**, la afinación.

Qué significa:

- **Usar la app en tu PC:** no impone nada.
- **Repartir la app, con cambios o sin ellos:** Ráfaga Studio entero tiene licencia GPL-3.0, compatible con estas
  librerías. Quien la reparta debe respetar la GPLv3: dar también el código, con la misma licencia.

Además, el programa **FFmpeg** que instala imageio-ffmpeg es una compilación **GPLv3** (con x264) y lo usan todas las
exportaciones de video. La app lo ejecuta como un programa aparte, así que no obliga a publicar el código de la app.
Pero quien distribuya la app junto con ese `ffmpeg.exe` debe incluir su licencia GPLv3 y ofrecer su código fuente, o
cambiarlo por una compilación LGPL.

Las demás licencias del proyecto (MIT, BSD, Apache, ISC, LGPL…) permiten el uso comercial. Las LGPL (PySide6/Qt,
edge-tts, lameenc, soxr) se usan como librerías que se instalan aparte y que el usuario puede cambiar, como pide esa
licencia.

## Modelos de IA que usa por defecto

| Modelo | Para qué | Licencia |
|---|---|---|
| FLUX.1 schnell (Black Forest Labs) | Imágenes (Cloudflare, Space oficial de Hugging Face, Replicate y Pollinations sin clave) | Apache 2.0 |
| Z-Image Turbo (Alibaba Tongyi) | Imágenes con tu cuenta gratis de Pollinations | Apache 2.0 |
| FLUX.1 Kontext [pro] (Black Forest Labs) | Anuncios con tu producto real, con Pollinations | Modelo cerrado: se aplican las condiciones de Pollinations y Black Forest Labs |
| Wan 2.2 (Alibaba) | Animar imágenes: TI2V-5B en tu nube Modal; en Hugging Face, un Space público de terceros (zerogpu-aoti) con Wan 2.2; y Pollinations (wan-2.2-fast) | Apache 2.0 |
| EchoMimicV3-Flash (Ant Group), con Wan2.1-Fun-V1.1-1.3B-InP (Alibaba PAI) y chinese-wav2vec2-base (Tencent) | Avatar IA (tu foto habla con tu voz) en tu nube Modal | Apache 2.0 (EchoMimicV3 y Wan2.1-Fun); MIT (chinese-wav2vec2-base) |
| Wan 2.2 S2V (Alibaba) | Avatar IA gratis, solo si lo marcas: el Space oficial de Wan en Hugging Face, que usa un modelo destilado en la API de Alibaba Cloud | Servicio de Alibaba Cloud Model Studio: sus condiciones |
| Gemini Flash Image «Nano Banana» (Google) | Imágenes, solo si eliges Gemini para las imágenes (de pago); la app usa el más nuevo de precio conocido de tu clave | Modelo cerrado: condiciones de la API de Gemini |
| Gemini Omni (Google) | Video animado con voz, con tu clave de Gemini (de pago); la app usa el más capaz que ofrezca tu clave | Modelo cerrado: condiciones de la API de Gemini |
| Kling (Kuaishou) | Animar escenas y escenas que hablan, solo si eliges Kling en «Claves de IA» (de pago); la app usa el mejor modelo que permita tu cuenta | Modelo cerrado: condiciones de la API de Kling AI (Kling AI Pte. Ltd.) |
| Seedance (ByteDance), en BytePlus ModelArk | Animar escenas y escenas que hablan, solo si eliges Seedance en «Claves de IA» (de pago); la app usa el mejor modelo que permita tu cuenta | Modelo cerrado: condiciones de BytePlus ModelArk |
| GPT-OSS 20B (OpenAI), vía Pollinations | Texto gratis sin clave (el modelo exacto lo decide Pollinations) | Apache 2.0 |
| Whisper (OpenAI), con faster-whisper | Entender lo que le dices al Director: siempre en tu PC. Subtítulos, shorts y video musical: en tu PC, salvo que conectes Groq u OpenAI para transcribir (entonces se hace en su nube con Whisper) | MIT |
| Demucs (Meta) | Separar voz y pista, en tu PC | MIT |

Los modelos de las IA que conectes con tu clave (Claude, GPT, Gemini…) se usan según las condiciones de cada
proveedor.

## Recursos gráficos

| Recurso | Licencia |
|---|---|
| Iconos Lucide (`assets/iconos`) | ISC (y MIT para los iconos que vienen de Feather; ver `assets/iconos/LICENSE`) |
| Fuentes de Google Fonts: Anton, Bebas Neue, Cinzel Decorative, Creepster, Grenze Gotisch, Lora, Metal Mania, Montserrat, New Rocker, Oswald, Pacifico, Pirata One, Playfair Display, Poppins (`assets/fuentes`) | SIL Open Font License 1.1 (ver `assets/fuentes/OFL.txt`) |
| FFmpeg 7.1 (compilación essentials de gyan.dev, incluida en imageio-ffmpeg) | GPLv3 (compilado con --enable-gpl --enable-version3, x264 y x265) |

## Servicios de terceros

Al usarlos se aplican sus condiciones y sus políticas de privacidad: Anthropic, OpenAI, Google (Gemini y Lyria),
Groq, OpenRouter, xAI, DeepSeek, Cloudflare Workers AI, Hugging Face, Pollinations, Replicate, Modal, ElevenLabs,
Kling AI (Kuaishou), BytePlus ModelArk (ByteDance, para Seedance), Microsoft (voces de Edge, con edge-tts) y YouTube y los demás sitios de los que descargues videos (con yt-dlp).
OpenRouter y Pollinations reenvían tu pedido al proveedor del modelo que usan (por ejemplo OpenAI o Black Forest Labs),
que también lo trata según su política.

Sin que conectes nada, la app también contacta con: Cloudflare (una consulta para elegir el idioma por país, la
primera vez), PyPI (al instalar y en cada arranque, para actualizar yt-dlp), PyTorch y NuGet de Microsoft (al instalar, para bajar las librerías y Python), Hugging Face (para
bajar el modelo Whisper la primera vez) y Meta (`dl.fbaipublicfiles.com`, para bajar el modelo Demucs la primera vez).
Solo se descargan programas y modelos: no se envía tu contenido.

## Librerías de Python

Las versiones exactas que instalan el instalador y `Ráfaga Studio.bat` (`requirements.lock` y `requirements-torch.lock`; yt-dlp y
yt-dlp-ejs se actualizan solos al abrir la app), con la licencia que declara cada paquete:

| Paquete | Versión | Licencia |
|---|---|---|
| aiohappyeyeballs | 2.7.1 | Python Software Foundation License |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT |
| aiosignal | 1.4.0 | Apache Software License |
| annotated-types | 0.8.0 | MIT |
| anthropic | 2.1.0 | Apache Software License |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| av | 19.0.2 | BSD-3-Clause |
| cbor2 | 6.1.5 | MIT |
| certifi | 2026.10.19 | Mozilla Public License 2.0 (MPL 2.0) |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| cloudpickle | 3.1.2 | BSD License |
| colorama | 0.4.6 | BSD License |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| ctranslate2 | 4.8.3 | MIT |
| decorator | 5.3.1 | BSD-2-Clause |
| demucs | 4.1.0 | MIT License |
| docstring_parser | 0.18.0 | MIT License |
| edge-tts | 7.3.1 | GNU Lesser General Public License v3 (LGPLv3) |
| einops | 0.8.2 | MIT License |
| faster-whisper | 1.2.1 | MIT License |
| filelock | 4.2.4 | MIT |
| flatbuffers | 25.12.19 | Apache Software License |
| formulaic | 1.2.2 | MIT |
| frozenlist | 1.8.0 | Apache-2.0 |
| fsspec | 2026.9.0 | BSD-3-Clause |
| gradio_client | 2.7.2 | Apache-2.0 |
| grpclib | 0.4.9 | BSD License |
| h11 | 0.16.0 | MIT License |
| h2 | 4.4.1 | MIT |
| hf-xet | 1.7.0 | Apache-2.0 |
| hpack | 4.2.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.16.0 | BSD-3-Clause |
| httpx | 0.28.1 | BSD License |
| httpx2 | 2.16.0 | BSD-3-Clause |
| huggingface_hub | 2.2.0 | Apache Software License |
| hyperframe | 6.1.0 | MIT License |
| idna | 3.20 | BSD-3-Clause |
| imageio-ffmpeg | 0.6.0 | BSD License |
| interface_meta | 2.0.1 | MIT |
| Jinja2 | 3.1.6 | BSD License |
| jiter | 0.17.0 | MIT |
| joblib | 1.6.0 | BSD-3-Clause |
| json_repair | 0.64.1 | MIT |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| julius | 0.2.8 | MIT License |
| lameenc | 1.9.0 | LGPL-3.0-or-later |
| lazy-loader | 0.6 | BSD-3-Clause |
| librosa | 1.0.0 | ISC License (ISCL) |
| llvmlite | 0.50.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception |
| markdown-it-py | 4.2.0 | MIT License |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| matchering | 2.0.6 | GNU General Public License v3 (GPLv3) |
| mcp | 2.3.0 | MIT License |
| mcp-types | 2.3.0 | MIT License |
| mdurl | 0.1.2 | MIT License |
| modal | 1.6.2 | Apache-2.0 |
| mpmath | 1.3.0 | BSD License |
| msgpack | 1.2.3 | Apache-2.0 |
| multidict | 7.1.0 | Apache-2.0 |
| narwhals | 2.27.1 | MIT |
| networkx | 3.6.1 | BSD-3-Clause |
| numba | 0.68.0 | BSD License |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| onnxruntime | 1.31.0 | MIT License |
| openai | 3.36.0 | Apache-2.0 |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pandas | 3.0.6 | BSD License |
| patsy | 1.0.3 | BSD License |
| pedalboard | 0.9.26 | GNU General Public License v3 (GPLv3) |
| pip | 26.2.2 | MIT |
| platformdirs | 4.13.5 | MIT |
| pooch | 1.9.0 | BSD-3-Clause |
| praat-parselmouth | 0.4.7 | GNU General Public License v3 or later (GPLv3+) |
| propcache | 0.5.4 | Apache-2.0 |
| protobuf | 7.36.2 | 3-Clause BSD License |
| psola | 0.0.1 | GPLv3 |
| pycparser | 3.11 | BSD-3-Clause |
| pydantic | 2.14.1 | MIT |
| pydantic_core | 2.50.1 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| PyJWT | 2.15.1 | MIT |
| pypar | 0.0.6 | MIT License |
| PySide6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6_Addons | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6_Essentials | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6_Pdf | 6.12.0.140 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6_WebEngine | 6.12.0.140 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| python-dateutil | 2.9.0.post0 | BSD License |
| python-multipart | 0.0.32 | Apache-2.0 |
| pywin32 | 312 | Python Software Foundation License |
| PyYAML | 6.0.3 | MIT License |
| referencing | 0.37.0 | MIT |
| requests | 2.34.2 | Apache Software License |
| resampy | 0.4.3 | ISC License (ISCL) |
| rich | 15.0.0 | MIT License |
| rpds-py | 2026.9.1 | MIT |
| safetensors | 0.8.0 | Apache Software License |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| scipy | 1.18.1 | BSD License |
| setuptools | 84.2.1 | MIT |
| shiboken6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| six | 1.17.0 | MIT License |
| sniffio | 1.3.1 | MIT License |
| sounddevice | 0.5.6 | MIT |
| soundfile | 0.14.0 | BSD License |
| soxr | 1.1.0 | LGPL-2.1-or-later |
| sphn | 0.2.1 | Apache-2.0 |
| sse-starlette | 3.5.0 | BSD-3-Clause |
| starlette | 1.9.0 | BSD-3-Clause |
| statsmodels | 0.15.0 | BSD-3-Clause |
| sympy | 1.14.0 | BSD License |
| synchronicity | 0.12.6 | Apache Software License |
| tabulate | 0.10.0 | MIT |
| threadpoolctl | 3.7.0 | BSD-3-Clause |
| tokenizers | 0.23.3 | Apache Software License |
| toml | 0.10.2 | MIT License |
| torch | 2.14.1+cpu | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT |
| torchaudio | 2.11.0+cpu | BSD License |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| truststore | 0.10.5 | MIT |
| types-certifi | 2021.10.8.3 | Apache Software License |
| types-toml | 0.10.8.20260518 | Apache-2.0 |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.5 | Apache-2.0 |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| watchfiles | 1.3.0 | MIT License |
| wrapt | 2.5.1 | BSD-2-Clause |
| yarl | 1.25.1 | Apache-2.0 |
| yt-dlp | 2026.10.21 | Unlicense |
| yt-dlp-ejs | 0.8.0 | Unlicense AND MIT AND ISC |
