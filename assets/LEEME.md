# Recursos de diseño incluidos

Los iconos (`iconos/`) y las fuentes (`fuentes/`) son de terceros con licencia libre; aquí está de dónde salió cada
cosa y cómo comprobarlo. El logo (`icono.*`), la portada (`portada-github.png`) y la mascota Rafa (`mascota.jpg`) son de Ráfaga Studio™, con todos los
derechos reservados.
Lo bajó y validó un script aparte (fuera del proyecto): integridad del paquete, nombres de archivo seguros y
contenido revisado antes de copiarlo aquí.

## Iconos — `iconos/`

- **Origen:** paquete npm `lucide-static` versión **1.57.0** (<https://lucide.dev>),
  `https://registry.npmjs.org/lucide-static/-/lucide-static-1.57.0.tgz`
- **Licencia:** ISC (con la parte heredada de Feather bajo MIT); texto completo en `iconos/LICENSE`
  (sha256 `b495047bd93a9b06913511076f504daba17d5bbeb3e0650f3bb53a4220329c57`).
- **Integridad del paquete** (`dist.integrity` del registro npm, comprobada ANTES de extraer):
  `sha512-nuf4YoaKt3Pq9scXVQ71SLr0Q1/UZiTcfBBivFsCVL6biAzPplTikVWXLetBmK3oFEJS6f2L1rzgEsoJN/Ce0Q==`
- **Qué se extrajo:** solo `package/icons/*.svg` con nombre `[a-z0-9-]` (2154 iconos), revisados uno a uno
  (sin DOCTYPE, scripts, enlaces ni estilos: solo formas SVG), y las etiquetas de búsqueda de `package/tags.json`
  en `iconos/etiquetas.json` (1890 iconos con etiquetas).

## Fuentes — `fuentes/`

- **Origen:** <https://github.com/google/fonts>, commit fijo **`45e3d5269e4a17d823f6d84470bc084dc5ae46f6`**, carpeta `ofl/`.
  Cada archivo se comparó con el blob de git de ese commit y se comprobó que el `METADATA.pb` de su familia dice
  `license: "OFL"`.
- **Licencia:** SIL Open Font License 1.1 (OFL); los textos de cada familia, con sus derechos de autor, en
  `fuentes/OFL.txt`. Se pueden usar en diseños comerciales; no se pueden vender las fuentes por sí solas.

| Familia | Archivo | Ruta en google/fonts | sha256 |
|---|---|---|---|
| Montserrat | `Montserrat-Italic[wght].ttf` | `ofl/montserrat/Montserrat-Italic[wght].ttf` | `51607f316bc020e59f03cbf51543eecffbea501c0b31d73e5b82927c5cca442c` |
| Montserrat | `Montserrat[wght].ttf` | `ofl/montserrat/Montserrat[wght].ttf` | `0f7b311b2f3279e4eef9b2f968bcdbab6e28f4daeb1f049f4f278a902bcd82f7` |
| Poppins | `Poppins-Bold.ttf` | `ofl/poppins/Poppins-Bold.ttf` | `983676516167748b74de6f4771fb384c664fd913acb8b471122ecacf5da5ea6c` |
| Poppins | `Poppins-BoldItalic.ttf` | `ofl/poppins/Poppins-BoldItalic.ttf` | `3572ac8116a0ac7317d342262b29937bcbaf94d8f03f90df6fe666fa7e2fb43a` |
| Poppins | `Poppins-Italic.ttf` | `ofl/poppins/Poppins-Italic.ttf` | `4fa76ae75b40f926420514044722cb97f32186cafd3b38263cc34dad7174d46d` |
| Poppins | `Poppins-Regular.ttf` | `ofl/poppins/Poppins-Regular.ttf` | `7e65201e9b79159e2300267cc885e16c8dcef2424cdfa09a29bfb0980a94a7ba` |
| Bebas Neue | `BebasNeue-Regular.ttf` | `ofl/bebasneue/BebasNeue-Regular.ttf` | `08e4623805102d819f58601e46e345648846075e363b2ceb23313c2d1c83ec73` |
| Anton | `Anton-Regular.ttf` | `ofl/anton/Anton-Regular.ttf` | `a4ba3a92350ebb031da0cb47630ac49eb265082ca1bc0450442f4a83ab947cab` |
| Oswald | `Oswald[wght].ttf` | `ofl/oswald/Oswald[wght].ttf` | `5b38c246e255a12f5712d640d56bcced0472466fc68983d2d0410ec0457c2817` |
| Playfair Display | `PlayfairDisplay-Italic[wght].ttf` | `ofl/playfairdisplay/PlayfairDisplay-Italic[wght].ttf` | `a5e26dc5e2e77fb2803a0bf02fd4f81ee136ec8dea863ccdb0c59a263b21378b` |
| Playfair Display | `PlayfairDisplay[wght].ttf` | `ofl/playfairdisplay/PlayfairDisplay[wght].ttf` | `c40f2293766a503bc70cce9e512ef844a4ccb7cbcde792fe2ea31d191917d8d6` |
| Pacifico | `Pacifico-Regular.ttf` | `ofl/pacifico/Pacifico-Regular.ttf` | `5b6c0d5334a7bf77dea52b975c5a0c408878c0f7115ed5b6fb151f634b7bf701` |
| Lora | `Lora-Italic[wght].ttf` | `ofl/lora/Lora-Italic[wght].ttf` | `22d8d8854b53807aa664ca34f2031a9ed57a1d0dea296b8b96cdd3aad937a2b3` |
| Lora | `Lora[wght].ttf` | `ofl/lora/Lora[wght].ttf` | `822a6621ccbe8d97d20ac88c1c41f5615c9c2c202eaa75f272cd452aac6475a7` |
| Pirata One | `PirataOne-Regular.ttf` | `ofl/pirataone/PirataOne-Regular.ttf` | `5347a2e155589ecf667d4b766613c8ee003edde9f83717fd24c09599a4b1ecc0` |
| Grenze Gotisch | `GrenzeGotisch[wght].ttf` | `ofl/grenzegotisch/GrenzeGotisch[wght].ttf` | `701b299d8dc002a2b4bea2ff0f1272c0e4081a2835914354804565c410d0c637` |
| Metal Mania | `MetalMania-Regular.ttf` | `ofl/metalmania/MetalMania-Regular.ttf` | `4b95f0e55b291990c26a7b68818b20c1b728a8be05a34982b7bb4736c46c19ea` |
| New Rocker | `NewRocker-Regular.ttf` | `ofl/newrocker/NewRocker-Regular.ttf` | `28a499ce5b8bcf0652f8b2e25135183eaddf0c3c8c3e251259b075c71d1ef14c` |
| Creepster | `Creepster-Regular.ttf` | `ofl/creepster/Creepster-Regular.ttf` | `402aeb734586c74aecd3dbdc454589b1fb12e2e1c71f782fd019ae68066d9f44` |
| Cinzel Decorative | `CinzelDecorative-Regular.ttf` | `ofl/cinzeldecorative/CinzelDecorative-Regular.ttf` | `5b862be329103ad287a10f0a53e27a40e8cc519999253f1a0223e2dc330b10b8` |
| Cinzel Decorative | `CinzelDecorative-Bold.ttf` | `ofl/cinzeldecorative/CinzelDecorative-Bold.ttf` | `e854e68a388aa50d742a4415c1ae5c17a617ef7956c95a70021d0a4a44f20518` |

Las siete de abajo (góticas y decorativas, para títulos) se bajaron después del mismo commit, cada archivo a una
carpeta aislada; se comprobó la cabecera TrueType y el blob de git antes de copiarlo. UnifrakturMaguntia y
MedievalSharp se descartaron: la familia que `recursos.fuentes()` saca del nombre del archivo no sería la real.

## Emojis

No se incluyen: se usa la fuente de emoji del sistema (Segoe UI Emoji en Windows).
