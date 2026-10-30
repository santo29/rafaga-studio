"""Calidad de lo que sale (el informe de uso real): ortografía antes de quemar o publicar, karaoke con la letra escrita,
anuncios con la foto real del producto, shorts a la medida y sin voz, la duración pedida, acotaciones y títulos,
música de fondo, el glosario dominicano de las imágenes, mensajes y voces. Sin red ni claves de verdad: ninguna IA de
pago se llama (las IA son falsas). python -m pruebas.calidad"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx
import numpy as np

os.environ.setdefault("RAFAGA_IDIOMA", "es")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from motor import anuncios, cabina, claves, desde_prompt, herramientas, ia, musica, serie, shorts, video  # noqa: E402
from motor import actividad, video_musical  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="rafaga-calidad-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # nunca las claves del usuario
serie.CARPETA = tmp / "series"


def carpeta_nueva():
    """Cada trabajo en su carpeta de proyectos: dos en el mismo segundo tendrían el mismo nombre."""
    nueva = Path(tempfile.mkdtemp(prefix="proyectos-", dir=tmp))
    for modulo in (desde_prompt, anuncios, shorts, musica, video_musical, cabina):
        modulo.PROYECTOS = nueva
    return nueva


carpeta_nueva()


def hacer(nombre, *args) -> Path:
    video.ffmpeg(*args, tmp / nombre)
    return tmp / nombre


def cuadro(archivo: Path, segundo: float) -> np.ndarray:
    """El fotograma de ese segundo, en RGB."""
    w, h = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", video._leer_ffmpeg("-i", archivo)).groups()
    datos = subprocess.run([video.FFMPEG, "-v", "error", "-ss", str(segundo), "-i", str(archivo), "-frames:v", "1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(datos, np.uint8).reshape(int(h), int(w), 3).astype(int)


# La IA de texto falsa (lo que haría Groq): corrige como en el informe, o se inventa otra frase (eso no vale)
CORRIGE = {"FUSEL ESTE AROMA": "HUELE ESTE AROMA", "Deseño": "Deseo", "Rafa no doubles": "Rafa no dobles",
           "Pesadelos con robots gigantes": "Pesadillas con robots gigantes",
           "el malecón es nostro": "el malecón es nuestro", "Miren que bien": "Miren qué bien",
           "Subimos al malecón": "Subimos al malecón", "El malecón es nostro": "El malecón es nuestro",
           "a bailar con mi gente, el malecón es nostro": "a bailar con mi gente, el malecón es nuestro",
           "una cancion normal": "otra frase distinta y mucho más larga que la de antes",  # reescribe: no vale
           "#CaféBrise": "Café Brisa"}  # deja de ser hashtag: no vale
usadas = []


def corrector(c, instrucciones, pedido, esquema, rapido=False):
    usadas.append(c["proveedor"])
    assert instrucciones == ia.ORTOGRAFIA and esquema is ia._ESQUEMA_ORTOGRAFIA
    return {"textos": [CORRIGE.get(x, x) for x in json.loads(pedido)["textos"]]}


texto_con_real = ia._texto_con
ia._texto_con = corrector
try:
    # ---------- 3. Ortografía: sin IA que responda, las tildes y eñes más comunes ----------
    assert ia.ortografia(["Un sueno pequeno de mas", "PEQUENOS DISENOS", "la cancion", "#Musica", "passion"], "es") \
        == ["Un sueño pequeño de más", "PEQUEÑOS DISEÑOS", "la canción", "#Música", "passion"]
    assert ia.ortografia(["mas cafe"], "en") == ["mas cafe"]  # en otro idioma, nada de tildes del español
    assert usadas == []  # sin clave de texto no se pregunta a nadie (la gratis sin clave espera 30 s por pedido)
    # Las mayúsculas de un hashtag, letra por letra (salía «#Cinedecienciaficción»); «sabia» puede ser el adjetivo, y
    # con mayúscula a mitad de frase es un nombre (Nina, Montana)
    assert ia._tildes("#CineDeCienciaFiccion #ModoVacacion") == "#CineDeCienciaFicción #ModoVacación"
    assert ia._tildes("Una decisión sabia, dice Nina Simone en Montana.") == \
        "Una decisión sabia, dice Nina Simone en Montana."
    assert ia._tildes("Mas facil.\nNino feliz, ¿Mas?") == "Más fácil.\nNiño feliz, ¿Más?"
    # Con Groq (gratis) conectado se le pide a él, aunque la elegida para los guiones sea otra (de pago)
    claves.guardar({"proveedor": "anthropic", "clave": "sk-ant-prueba", "usos": ["texto"]})
    claves.guardar({"proveedor": "groq", "clave": "gsk_prueba", "usos": ["texto"]})
    claves.elegir_por_defecto("texto", "anthropic")
    textos = list(CORRIGE) + ["", "La naturaleza es sabia", "Nina baila", "Cafe Brisa"]
    hechos = ia.ortografia(textos, "es")
    assert usadas == ["groq"], usadas
    claves.borrar("anthropic")  # nada de Claude de aquí en adelante (investigar_web lo llamaría de verdad)
    assert hechos[:6] == ["HUELE ESTE AROMA", "Deseo", "Rafa no dobles", "Pesadillas con robots gigantes",
                          "el malecón es nuestro", "Miren qué bien"], hechos
    # Lo que cambia de frase no se usa (y lleva las tildes de respaldo); lo que la IA dejó igual, igual: «sabía»,
    # «Niña» o «Café Brisa» estropeaban palabras y marcas bien escritas
    assert hechos[9:] == ["una canción normal", "#CaféBrise", "", "La naturaleza es sabia", "Nina baila",
                          "Cafe Brisa"], hechos
    # Dentro de diccionarios (en su sitio), con listas de hashtags, y si la IA falla, el texto sigue como vino
    v = {"angulo": "Deseño", "hashtags": ["#CaféBrise", "#Musica"], "narracion": "FUSEL ESTE AROMA", "otro": 1}
    ia.repasar([v], ("angulo", "hashtags", "narracion", "falta"), "es")
    assert v == {"angulo": "Deseo", "hashtags": ["#CaféBrise", "#Musica"], "narracion": "HUELE ESTE AROMA", "otro": 1}

    def caida(*a):
        raise ia.SinServicio("402 sin saldo")
    ia._texto_con = caida
    avisos = []
    assert ia.ortografia(["Miren que bien", "mas"], "es", avisos) == ["Miren que bien", "más"]
    v = {"angulo": "mas"}
    ia.repasar([v], ("angulo",), "es", avisos)  # el aviso, una vez por trabajo
    assert v == {"angulo": "más"} and avisos == ["No se pudo repasar la ortografía (Groq: 402 sin saldo)."], avisos
    # y el «no atendió» queda en la actividad de la IA (_texto_con lo deja a quien llama)
    apunte = actividad.ultimas(1)[0]
    assert (apunte["proveedor"], apunte["que"], apunte["resultado"]) == ("groq", "texto", "fallo"), apunte
    ia._texto_con = corrector
    usadas.clear()

    # ---------- 2. Karaoke: la letra ESCRITA con los tiempos de lo que oyó Whisper ----------
    def oido(texto, desde=0.0):
        return [{"palabra": p, "inicio": desde + i * 0.5, "fin": desde + i * 0.5 + 0.4}
                for i, p in enumerate(texto.split())]
    escrita = "Subimos al malecón a bailar con mi gente, el malecón es nuestro".split()
    oidas = oido("SUVIMOS AL MALECÓN A VAI LA CON MI GENTE EL MALECÓN ES NOSTRO")
    alineada = video_musical.alinear(escrita, oidas)
    assert [p["palabra"] for p in alineada] == escrita, alineada
    assert alineada[0]["inicio"] == 0 and alineada[-1]["fin"] == oidas[-1]["fin"]
    assert all(a["inicio"] <= a["fin"] <= b["inicio"] + 1e-9 for a, b in zip(alineada, alineada[1:]))
    bailar = alineada[4]  # «bailar» ocupa lo que Whisper oyó como «VAI LA»
    assert bailar["inicio"] == oidas[4]["inicio"] and abs(bailar["fin"] - oidas[5]["fin"]) < 1e-9, bailar
    # Lo que no oyó se reparte en el hueco entre sus vecinas; lo que oyó sin estar escrito no sale
    alineada = video_musical.alinear("hoy vamos todos al malecón".split(), oido("hoy eh al malecón"))
    assert [p["palabra"] for p in alineada] == ["hoy", "vamos", "todos", "al", "malecón"], alineada
    assert 0.4 <= alineada[1]["inicio"] < alineada[2]["fin"] <= 1.0, alineada
    # Un coro escrito una vez y cantado dos: la segunda vez también sale lo escrito
    coro = "dale que dale que el domingo es pa gozar"
    alineada = video_musical.alinear(f"vamos pa la playa {coro}".split(),
                                     oido(f"vamos pa la playa {coro}") + oido(coro.upper(), 20))
    assert len(alineada) == 4 + 2 * 9 and alineada[-1]["palabra"] == "gozar" and alineada[-1]["inicio"] > 20
    assert video_musical.alinear(escrita, []) == []

    # El video musical entero (sin red): el karaoke dibuja la letra escrita y el título es el de la canción
    cancion = hacer("cancion.wav", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-metadata",
                    "title=Domingo en el Malecón")
    karaoke, reales = [], (ia.transcribir, ia.texto_json, ia.imagen, ia.video_desde_imagen, video.segmento_mudo,
                           video.unir, video.con_cancion)
    ia.transcribir = lambda audio, **k: oidas
    ia.texto_json = lambda i, p, e: {"estilo_visual": "film", "escenas": ["people dancing with a güira"],
                                     "descripcion": "Un domingo de malecón", "hashtags": ["#Merengue"]}
    dibujos = []
    ia.imagen = lambda prompt, w, h, d, *a: dibujos.append(prompt) or d
    ia.video_desde_imagen = lambda *a, **k: None
    video.segmento_mudo = lambda img, s, f, destino, i, clip=None: destino
    video.unir = lambda partes, d: d
    video.con_cancion = lambda visual, audio, f, palabras, d: karaoke.append(palabras) or d
    try:
        letra = "Domingo en el Malecón\n\n[Chorus]\nSubimos al malecón\n(Shout: ¡Wepa!)\na bailar con mi gente, " \
                "el malecón es nostro"
        carpeta_nueva()
        r = video_musical.crear(str(cancion), letra=letra)
        assert r["titulo"] == "Domingo en el Malecón", r["titulo"]  # de las etiquetas, no «cancion»
        assert [p["palabra"] for p in karaoke[-1]] == escrita, karaoke[-1]  # sin «SUVIMOS», «VAI LA» ni «Shout»
        assert "perforated" in dibujos[-1]  # la güira, descrita (9)
        # Una letra que no es la que suena (una ruta, o solo un trozo del coro) no sustituye lo que se oye
        for mala in ("letra.txt", "Subimos al malecón"):
            carpeta_nueva()
            r = video_musical.crear(str(cancion), letra=mala)
            assert karaoke[-1] == oidas and any("no coincide con lo que se oye" in a for a in r["avisos"]), r
        carpeta_nueva()
        r = herramientas.crear_video_musical(str(cancion), titulo="Mi título")
        assert json.loads(r)["titulo"] == "Mi título"
    finally:
        (ia.transcribir, ia.texto_json, ia.imagen, ia.video_desde_imagen, video.segmento_mudo, video.unir,
         video.con_cancion) = reales

    # ---------- 7. Títulos de verdad ----------
    proyecto = tmp / "proyectos" / "20261026-192404-musica"
    (proyecto / "demucs" / "htdemucs" / "original").mkdir(parents=True)
    (proyecto / "proyecto.json").write_text(json.dumps({"titulo": "Domingo  en el\nMalecón"}), encoding="utf-8")
    sin_etiqueta = hacer("mi_cancion_nueva.wav", "-f", "lavfi", "-i", "sine=duration=1")
    for ruta in (proyecto / "cancion.mp3", proyecto / "demucs" / "htdemucs" / "original" / "vocals.wav"):
        ruta.write_bytes(sin_etiqueta.read_bytes())
        assert video.titulo_cancion(ruta) == "Domingo en el Malecón", ruta  # también la voz separada
    solo_letra = tmp / "letra_sola"
    solo_letra.mkdir()
    (solo_letra / "letra.txt").write_text("Viernes de dembow\n\n[Chorus]\nDale", encoding="utf-8")
    (solo_letra / "cancion.wav").write_bytes(sin_etiqueta.read_bytes())
    assert video.titulo_cancion(solo_letra / "cancion.wav") == "Viernes de dembow"
    assert video.titulo_cancion(cancion) == "Domingo en el Malecón"  # la etiqueta «title» del archivo
    assert video.titulo_cancion(sin_etiqueta) == "mi cancion nueva"
    separar_real = cabina.separar
    cabina.separar = lambda original, carpeta, aviso: {"voz": original, "pista": original, "donde": "este PC"}
    try:
        carpeta_nueva()
        assert cabina.separar_cancion(str(proyecto / "cancion.mp3"))["titulo"] == "Domingo en el Malecón"
    finally:
        cabina.separar = separar_real
    corto = desde_prompt.titulo_corto("la pareja baila merengue en el malecón bajo el brazo de él con la falda al "
                                      "viento y el sol")
    assert corto == "La pareja baila merengue en el malecón bajo el…" and len(corto) <= 50, corto
    assert desde_prompt.titulo_corto("Un gato que baila. Con sombrero") == "Un gato que baila"
    assert desde_prompt.titulo_corto("¿Qué pasa en el malecón? Mira") == "¿Qué pasa en el malecón?"  # con su «?»
    assert desde_prompt.titulo_corto("¡Dale, mi gente!") == "¡Dale!"

    # ---------- 6. La canción para publicar: sin acotaciones ni marcas, con el hashtag de su género ----------
    letra = ("[Intro]\n(Shout: ¡Wepa, wepa!)\n[Chorus]\nEl malecón es nostro (Shout: ¡Dale!)\nque brilla el sol\n\n\n"
             "(Fade out with tambora and güira sound)\n(oh oh oh)")
    assert ia.sin_acotaciones(letra) == "El malecón es nostro\nque brilla el sol", ia.sin_acotaciones(letra)
    assert ia.sin_acotaciones("Mi amor (de verdad) te quiero") == "Mi amor (de verdad) te quiero"  # lo cantado se queda
    claves.guardar({"proveedor": "gemini", "clave": "AIza-prueba", "usos": ["musica"], "modelo_musica": "lyria-3.5"})
    reales = ia.texto_json, musica._gemini
    ia.texto_json = lambda i, p, e: {"titulo": "Domingo en el Malecón", "estilo": "merengue", "letra": letra,
                                     "descripcion": "Un merengue pa gozar", "hashtags": ["#DomingoEnElMalecón",
                                                                                      "#merenguetípico"]}
    musica._gemini = lambda c, estilo, letra, segundos: b"ID3cancion"
    try:
        carpeta_nueva()
        r = musica.crear("un merengue del malecón", "Merengue típico")
        publicado = r["resultados"][0]
        assert publicado["descripcion"] == "Un merengue pa gozar\n\nEl malecón es nuestro\nque brilla el sol", \
            publicado["descripcion"]  # corregida por la IA de texto (gratis) y sin «Shout» ni «Fade out»
        assert publicado["hashtags"] == ["#MerengueTípico", "#DomingoEnElMalecón"], publicado["hashtags"]
        assert "nunca de otro género" in " ".join(musica.INSTRUCCIONES.split())  # «#MúsicaRomántica» en un merengue
        assert "(Shout" in (Path(r["carpeta"]) / "letra.txt").read_text(encoding="utf-8")  # la del modelo, intacta
    finally:
        ia.texto_json, musica._gemini = reales
    claves.borrar("gemini")
    usadas.clear()

    # ---------- 1. Anuncios: la foto real del producto sale siempre ----------
    foto = hacer("taza.png", "-f", "lavfi", "-i", "color=c=red:s=200x200", "-frames:v", "1")
    plan = {"variantes": [{"angulo": "Deseño", "gancho": "g", "titulo": "Café Brisa Alta", "texto_anuncio": "Pídelo",
                           "hashtags": ["#CaféBrise"], "estilo_visual": "close-up hands, warm light", "escenas": [
                               {"narracion": "FUSEL ESTE AROMA", "imagen": "a steaming cup on a table"},
                               {"narracion": "Cada mañana.", "imagen": "a kitchen at sunrise"},
                               {"narracion": "Pídelo hoy.", "imagen": "a happy woman drinking coffee"}]}]}
    dibujos, con_foto, pegadas, cierres, narradas = [], [], [], [], []
    reales = (ia.texto_json, ia.imagen, ia.imagen_con_producto, ia.pegar_producto, ia.video_desde_imagen,
              desde_prompt.narrar, video.duracion, video.escena_de_imagen, video.unir, video.cierre, ia.investigar_web,
              ia.video_de_pago, ia.nota_pago, desde_prompt._ya_animada)
    ia.investigar_web = lambda pregunta: None
    ia.texto_json = lambda i, p, e: json.loads(json.dumps(plan))
    ia.imagen = lambda prompt, w, h, d, *a: dibujos.append(prompt) or d
    ia.imagen_con_producto = lambda prompt, f, w, h, d, realista=True, **k: con_foto.append(prompt) or d
    ia.pegar_producto = lambda prompt, f, w, h, d: pegadas.append(prompt) or d
    ia.video_desde_imagen = lambda *a, **k: None
    desde_prompt.narrar = lambda texto, voz, destino: narradas.append(texto) or []
    video.duracion = lambda p: 1.0
    escenas_de = []
    video.escena_de_imagen = lambda img, audio, f, palabras, escena, i: escenas_de.append(img) or escena
    video.unir = lambda partes, d: d
    video.cierre = lambda m, texto, f, d, producto=None: cierres.append((texto, producto)) or d
    try:
        # La IA (como Groq) no escribió «the product» en ninguna escena: la foto va en la del medio y en el cierre
        carpeta_nueva()
        r = anuncios.crear(str(foto), "Café Brisa Alta", "café de altura", "adultos", "PÍDELO HOY",
                           "Demostración del producto", variantes=1, segundos=15)
        assert len(con_foto) == 1 and con_foto[0].startswith("the product as the hero of the shot"), con_foto
        assert len(dibujos) == 2 and cierres[-1][0] == "PÍDELO HOY" and cierres[-1][1].name == "producto.png"
        assert narradas[0] == "HUELE ESTE AROMA" and r["resultados"][0]["titulo"].startswith("1. Deseo — ")  # (3)
        assert usadas == ["groq"]
        # Si la edición con referencia no atiende (402, no cobró; con Gemini llega como SinServicio), la foto se pega
        # sobre una escena nueva y se dice una vez por qué (ia.imagen_con_producto, la de verdad); si no sale ninguna
        # imagen, la foto sola (antes se repetía la escena anterior, sin el producto)
        def sin_saldo(*a, **k):
            httpx.Response(402, request=httpx.Request("POST", "https://x.example/v1/images/edits")).raise_for_status()

        def gemini_sin_saldo(*a, **k):  # lo que hace _imagen_gemini con un 402 (abajo, con su httpx falso)
            raise ia.SinServicio("Gemini respondió 402: sin saldo")
        referencia_real, puede_real = ia._con_referencia, ia.puede_referencia
        ia.imagen_con_producto, ia.puede_referencia = reales[2], lambda: True
        for falla in (sin_saldo, gemini_sin_saldo):
            ia._con_referencia, n = falla, len(pegadas)
            carpeta_nueva()
            r = anuncios.crear(str(foto), "Café Brisa Alta", "", "", "", "Demostración del producto", variantes=1,
                               segundos=15)
            assert len(pegadas) == n + 1 and len(r["avisos"]) == 2, r["avisos"]
            assert "La edición con la imagen de referencia falló (" in r["avisos"][1] and "402" in r["avisos"][1] \
                and "foto encima de un fondo nuevo" in r["avisos"][1], r["avisos"]
            assert "https://" not in r["avisos"][1] and "mozilla" not in r["avisos"][1]  # solo el servicio, sin enlaces
        ia._con_referencia, ia.puede_referencia = referencia_real, puede_real
        ia.imagen_con_producto = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Ninguna IA de imágenes"))
        escenas_de.clear()
        carpeta_nueva()
        r = anuncios.crear(str(foto), "Café Brisa Alta", "", "", "", "Demostración del producto", variantes=1,
                           segundos=15)
        assert escenas_de[1].name == "producto.png", escenas_de
        assert any("escena 2 no salió (Ninguna IA de imágenes)" in a and "foto de respaldo" in a
                   for a in r["avisos"]), r["avisos"]
        # Con video de pago, la foto de respaldo repetida no se anima: se cobraba un clip de Kling por cada escena con
        # la misma foto (las tres piden «the product» y no sale ninguna imagen)
        ia.texto_json = lambda i, p, e: {"variantes": [{**plan["variantes"][0], "escenas": [
            {"narracion": "Uno.", "imagen": "the product on a table"},
            {"narracion": "Dos.", "imagen": "hands holding the product"},
            {"narracion": "Tres.", "imagen": "the product in a kitchen"}]}]}
        ia.video_de_pago, ia.nota_pago = lambda: "kling", lambda pago, n: f"pagados {n}"
        desde_prompt._ya_animada = lambda clip, img: False
        animadas = []
        ia.video_desde_imagen = lambda img, prompt, f, s, destino, pago: animadas.append(img) or destino
        carpeta_nueva()
        r = anuncios.crear(str(foto), "Café Brisa Alta", "", "", "", "Demostración del producto", variantes=1,
                           segundos=15)
        assert animadas == [] and not any("pagados" in a for a in r["avisos"]), r["avisos"]
        assert sum("foto de respaldo" in a for a in r["avisos"]) == 3, r["avisos"]
    finally:
        (ia.texto_json, ia.imagen, ia.imagen_con_producto, ia.pegar_producto, ia.video_desde_imagen,
         desde_prompt.narrar, video.duracion, video.escena_de_imagen, video.unir, video.cierre,
         ia.investigar_web, ia.video_de_pago, ia.nota_pago, desde_prompt._ya_animada) = reales
    # Gemini sin saldo (402) dibujando es «no atendió» (SinServicio, no se cobró), como el 402 de la edición con
    # referencia: así los anuncios pegan la foto en vez de dejar la foto sola
    reales = ia.httpx.post, ia.modelo_imagen_gemini, ia.guardia.sin_bloqueo
    ia.httpx.post = lambda *a, **k: httpx.Response(402, json={"error": {"message": "sin saldo"}},
                                                   request=httpx.Request("POST", "https://x.example"))
    ia.modelo_imagen_gemini, ia.guardia.sin_bloqueo = lambda clave: "gemini-imagen", lambda: None
    try:
        ia._imagen_gemini({"clave": "AIza-prueba"}, "a cup", 64, 64, foto)
        raise AssertionError("debió fallar")
    except ia.SinServicio as error:
        assert "402" in str(error) and "sin saldo" in str(error), error
    finally:
        ia.httpx.post, ia.modelo_imagen_gemini, ia.guardia.sin_bloqueo = reales
    usadas.clear()
finally:
    ia._texto_con = texto_con_real
claves.borrar("groq")

# El cierre de verdad (FFmpeg): va DESPUÉS de la narración (sin el subtítulo gris debajo de la oferta) y lleva la foto
base = hacer("anuncio_base.mp4", "-f", "lavfi", "-i", "color=c=0x3060C0:s=1080x1920:r=30:d=1", "-f", "lavfi", "-i",
             "sine=frequency=440:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest")
hecho = video.cierre(base, "PÍDELO HOY", "9:16", tmp / "anuncio_cierre.mp4", producto=foto)
assert abs(video.duracion(hecho) - 4) < 0.15, video.duracion(hecho)
antes, despues = cuadro(hecho, 0.5), cuadro(hecho, 2.5)
assert abs(antes.mean(axis=(0, 1)) - cuadro(base, 0.5).mean(axis=(0, 1))).max() < 6  # la narración, sin tocar
w, h = video.FORMATOS["9:16"]
centro = despues[int(h * 0.55)][w // 2]  # la foto roja, en el centro y algo abajo (la oferta va arriba)
assert centro[0] > 200 and centro[1] < 60 and centro[2] < 60, centro
assert despues[h - 20][20].sum() < antes[h - 20][20].sum()  # el fondo, oscurecido
assert abs(video.duracion(video.cierre(base, "OFERTA", "9:16", tmp / "sin_foto.mp4")) - 4) < 0.15

# ---------- 4. Shorts: a la medida pedida, sin pisarse, y con videos sin voz ----------
frases = [{"palabra": f"p{i}." if i % 6 == 5 else f"p{i}", "inicio": i * 0.5, "fin": i * 0.5 + 0.4}
          for i in range(1440)]  # 12 minutos, una frase cada 3 s
clips = [{"inicio": 26.9, "fin": 39.7, "puntuacion": 90}, {"inicio": 39.3, "fin": 52.1, "puntuacion": 80},
         {"inicio": 80.0, "fin": 92.8, "puntuacion": 70}]
elegidos = shorts._elegir(clips, 3, 20, 45, frases, 720)
# El segundo momento ya sale casi entero en el primero alargado (hasta 48,2): no va otro short que empiece a mitad de
# lo suyo (salía 48,2-69,2, con 3,9 s de su momento y 17 s que la IA no eligió)
assert [c["puntuacion"] for c in elegidos] == [90, 70], elegidos
for c in elegidos:
    assert 20 <= c["fin"] - c["inicio"] <= 45, c
    propio = next(m for m in clips if m["puntuacion"] == c["puntuacion"])
    assert min(c["fin"], propio["fin"]) - max(c["inicio"], propio["inicio"]) >= 0.5 * (propio["fin"] - propio["inicio"])
a, b = sorted(elegidos, key=lambda c: c["inicio"])
assert a["fin"] <= b["inicio"], (a, b)  # nunca se pisan
assert any(abs(c["fin"] - 0.3 - p["fin"]) < 1e-9 for c in elegidos[:1] for p in frases if p["palabra"].endswith("."))
assert shorts._elegir([{"inicio": 2, "fin": 6, "puntuacion": 9}], 3, 20, 60, [], 12)[0] == \
    {"inicio": 0, "fin": 12, "puntuacion": 9}  # un video más corto que el mínimo: entero
# Sin voz (Big Buck Bunny): los momentos con más cambios de escena, que empiezan y acaban en un corte
mudo = hacer("mudo.mp4", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=10:d=30,drawbox=x=0:y=0:w=iw:h=ih:"
             "color=white:t=fill:enable='lt(mod(t,6),3)'", "-f", "lavfi", "-i", "sine=duration=30",  # música, sin voz
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest")
momentos = shorts.momentos_visuales(mudo, 30.0, 5, 10)
assert momentos and all(5 * 0.8 <= c["fin"] - c["inicio"] <= 10 for c in momentos), momentos
cortes = {3.0, 6.0, 9.0, 12.0, 15.0, 18.0, 21.0, 24.0, 27.0}
assert all(any(abs(c["fin"] - x) < 0.25 for x in cortes) or c["fin"] == 30 for c in momentos), momentos
assert momentos[0]["puntuacion"] > 0 and "titulo" not in momentos[0]  # el título, después (pruebas.compatibles)
pedidos, opciones = [], []
reales = shorts.descargar, video.recortar, ia.transcribir, ia.texto_json
shorts.descargar = lambda url, carpeta, progreso: (mudo, "Big Buck Bunny")
recortes = []
video.recortar = lambda original, ini, fin, formato, modo, palabras, destino: recortes.append((ini, fin, palabras)) \
    or destino
ia.transcribir = lambda audio, progreso=None: progreso(1) or []
ia.texto_json = lambda *a, **k: pedidos.append(a) or {"descripcion": "d", "hashtags": [], "tema": "Conejo gigante"}
try:
    carpeta_nueva()
    r = shorts.generar("https://www.youtube.com/watch?v=aqz-KE-bpKQ", cantidad=2, dur_min=5, dur_max=10)
    # Sin voz no se pide elegir momentos a la IA: solo la descripción, los hashtags y el tema, desde el título
    assert [p[0] for p in pedidos] == [shorts.INSTRUCCIONES_TITULO] and "no tiene voz" in r["avisos"][0], r
    assert [c["titulo"] for c in r["resultados"]] == ["Momento 1 de 2: Conejo gigante",
                                                     "Momento 2 de 2: Conejo gigante"], r
    pedidos.clear()
    assert all(not p and 4 <= fin - ini <= 10 for ini, fin, p in recortes), recortes
    (x0, x1, _), (y0, y1, _) = sorted(recortes)
    assert x1 <= y0
    # Con voz: el título y los hashtags, en el idioma de la app (el video puede hablar otro)
    ia.transcribir = lambda audio, progreso=None: frases[:60]
    ia.texto_json = lambda i, pedido, e: pedidos.append(pedido) or {"clips": [
        {"inicio": 0, "fin": 12.9, "titulo": "Pesadelos con robots gigantes", "descripcion": "d", "hashtags": [],
         "puntuacion": 9, "motivo": "m"}]}
    carpeta_nueva()
    r = shorts.generar("https://www.youtube.com/watch?v=x", cantidad=1, dur_min=20, dur_max=45)
    assert "Título, descripción y hashtags en Español" in pedidos[-1] and "idioma que diga el pedido" in \
        shorts.INSTRUCCIONES
    assert r["avisos"] == [] and 20 <= r["resultados"][0]["fin"] - r["resultados"][0]["inicio"] <= 30, r
finally:
    shorts.descargar, video.recortar, ia.transcribir, ia.texto_json = reales


class SinBajar:  # yt-dlp falso: solo mira con qué opciones se abre
    def __init__(self, opciones):
        opciones_vistas.append(opciones)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download):
        raise shorts.yt_dlp.utils.DownloadError("sin red en las pruebas")


opciones_vistas, real = [], shorts.yt_dlp.YoutubeDL
shorts.yt_dlp.YoutubeDL = SinBajar
try:
    shorts.descargar("https://www.youtube.com/watch?v=x", tmp)
    raise AssertionError("debió fallar")
except RuntimeError:
    assert opciones_vistas[0]["noprogress"] is True and opciones_vistas[0]["quiet"] is True  # sin barra en consola
finally:
    shorts.yt_dlp.YoutubeDL = real

# ---------- 5. crear_video: la duración pedida y el «¿» en los subtítulos ----------
largas = [{"narracion": "Esta es la primera frase de la escena con datos. Y esta es la segunda frase, más larga "
                        "todavía que la primera.", "imagen": "x"} for _ in range(5)]
assert desde_prompt.al_tiempo(largas, 30)
assert sum(len(e["narracion"].split()) for e in largas) / desde_prompt.PALABRAS_POR_SEGUNDO + 0.25 * len(largas) \
    <= 33, largas
assert not desde_prompt.al_tiempo([{"narracion": "Hola a todos.", "imagen": "x"}] * 3, 30)  # ya cabe: igual
# El guion del informe: 79 palabras que la voz de Emilio dijo en 37,3 s (el video salió de 38,6 con 30 pedidos). Con
# 2,5 palabras por segundo parecía caber y no se acortaba
informe = [{"narracion": x, "imagen": "x"} for x in (
    "El merengue dominicano es pura alegría, pero esconde historias fascinantes que casi nadie conoce.",
    "Primero, sus instrumentos unen tres continentes: la tambora africana, la güira taína y el acordeón europeo.",
    "Segundo, su paso típico nació cuando un pueblo entero imitó a un héroe de guerra herido para bailar con él.",
    "Tercero, fue prohibido por las élites por considerarlo vulgar, y hoy es Patrimonio de la Humanidad.",
    "¿Cuál dato te sorprendió más? Cuéntanos en los comentarios y ponte a bailar.")]
assert sum(len(e["narracion"].split()) for e in informe) == 79 and desde_prompt.al_tiempo(informe, 30)
assert sum(len(e["narracion"].split()) for e in informe) / 2.12 <= 30, informe  # a la velocidad real de la voz
muchas = [{"narracion": " ".join(["palabra"] * 30), "imagen": str(i)} for i in range(8)]
desde_prompt.al_tiempo(muchas, 30)
assert len(muchas) == 3 and [e["imagen"] for e in muchas][0] == "0" and muchas[-1]["imagen"] == "7"  # gancho y cierre
edge = [{"palabra": "Cuál", "inicio": 0, "fin": 0.3}, {"palabra": "dato", "inicio": 0.3, "fin": 0.6},
        {"palabra": "te", "inicio": 0.6, "fin": 0.7}, {"palabra": "sorprendió", "inicio": 0.7, "fin": 1.2},
        {"palabra": "más", "inicio": 1.2, "fin": 1.5}]
assert [p["palabra"] for p in desde_prompt.con_signos(edge, "¿Cuál dato te sorprendió más?")] == \
    ["¿Cuál", "dato", "te", "sorprendió", "más?"]
reales = ia.texto_json, ia.imagen, desde_prompt.narrar, video.duracion, video.escena_de_imagen, video.unir
guion = {"titulo": "3 datos del merengue", "descripcion": "d", "hashtags": ["#Musica"], "estilo_visual": "photo",
         "escenas": [{"narracion": "La güira suena así. Y la tambora la sigue con su ritmo de siempre.",
                      "imagen": "a man playing a guira"} for _ in range(6)]}
ia.texto_json = lambda i, p, e: json.loads(json.dumps(guion))
dibujos = []
ia.imagen = lambda prompt, w, h, d, *a: dibujos.append(prompt) or d
desde_prompt.narrar = lambda texto, voz, destino: []
video.duracion = lambda p: 1.0
video.escena_de_imagen = lambda img, audio, f, palabras, escena, i: escena
video.unir = lambda partes, d: d
try:
    carpeta_nueva()
    r = desde_prompt.generar("merengue", segundos=20)
    hecho = json.loads((Path(r["carpeta"]) / "guion.json").read_text(encoding="utf-8"))
    palabras = sum(len(e["narracion"].split()) for e in hecho["escenas"])
    assert palabras / desde_prompt.PALABRAS_POR_SEGUNDO + 0.25 * len(hecho["escenas"]) <= 22, hecho
    assert any("se acortó el guion" in a for a in r["avisos"]) and r["resultados"][0]["hashtags"] == ["#Música"]
    # 9: la güira y la tambora, descritas de verdad en el pedido de la imagen (salían una espátula y un djembé)
    assert all("perforated" in d for d in dibujos) and "two-headed barrel drum" in dibujos[0], dibujos[0]
finally:
    ia.texto_json, ia.imagen, desde_prompt.narrar, video.duracion, video.escena_de_imagen, video.unir = reales

# ---------- 9. Glosario dominicano: solo lo que se nombra, y los pesos solo en una escena dominicana ----------
bandera = desde_prompt.con_glosario("a beach with the bandera dominicana waving", "Un domingo en la playa")
assert "white cross" in bandera and "ultramarine blue" in bandera and "peso" not in bandera
puesto = desde_prompt.con_glosario("a street vendor stand", "Los yaniqueques cuestan poco dinero")
assert "fried dough" in puesto and desde_prompt.PESOS in puesto
assert desde_prompt.con_glosario("money on a table in a Paris cafe", "Ahorra dinero") == \
    "money on a table in a Paris cafe"
assert desde_prompt.con_glosario("a colmado at night", "").count("colmado is a small corner grocery") == 1
assert "motorcycle taxi" in desde_prompt.con_glosario("a motoconcho in traffic")
assert desde_prompt.con_glosario("the seguiras dance") == "the seguiras dance"  # dentro de otra palabra: nada
assert desde_prompt.PESOS in desde_prompt.con_glosario("a vendor counting RD$500 bills")  # con la cifra pegada
assert desde_prompt.PESOS in desde_prompt.con_glosario("a price tag of RD$ 1,500")

# ---------- 8. Música de fondo del editor: baja, sin silencio al final y con fundido ----------
fondo = {"id": "m1", "tipo": "musica", "archivo": "x.wav", "inicio": 0, "desde": 0, "hasta": 40.0, "volumen": 1,
         "entrada": 0, "salida": 0}
vueltas = herramientas.musica_de_fondo(fondo, 43.6)
assert [(v["inicio"], v["desde"], round(v["hasta"], 3)) for v in vueltas] == [(0.0, 0, 40.0), (40.0, 0, 3.6)]
assert all(v["volumen"] == herramientas.VOLUMEN_FONDO < 0.5 for v in vueltas)  # bajo la voz del video
assert vueltas[1]["entrada"] > 0 and 0 < vueltas[-1]["salida"] <= 1.81 and len({v["id"] for v in vueltas}) == 2
larga = herramientas.musica_de_fondo({**fondo, "hasta": 100.0}, 43.6)
assert len(larga) == 1 and larga[0]["hasta"] == 43.6 and larga[0]["salida"] == 2.0

# ---------- 10. Mensajes y voces ----------
avisos = []
foto_animar = hacer("animar.png", "-f", "lavfi", "-i", "color=c=blue:s=64x64", "-frames:v", "1")
real = ia.video_desde_imagen
ia.video_desde_imagen = lambda *a, **k: None
try:
    for elegido, esperado in ((None, "gratis primero"), ("modal", "tu nube Modal")):
        if elegido:
            claves.guardar({"proveedor": "modal", "clave": "ak-a as-b", "usos": ["video"]})
            claves.elegir_por_defecto("video", "modal")
        avisos.clear()
        carpeta_nueva()
        try:
            desde_prompt.animar_imagen(str(foto_animar), "que baile", aviso=lambda texto, f: avisos.append(texto))
        except ia.SinClave:
            pass
        assert esperado in avisos[0] and ("gratis" in avisos[0]) == (elegido is None), avisos
finally:
    ia.video_desde_imagen = real
    claves.borrar("modal")
personajes = [{"nombre": n} for n in ("Rafa", "Yari", "Don Tito", "Doña Ana", "Chepe")]
avisos = serie._asignar_voces(personajes, ["hombre", "mujer", "hombre", "mujer", "hombre"])
assert [p["voz"] for p in personajes] == ["es-DO-EmilioNeural", "es-DO-RamonaNeural", "es-PR-VictorNeural",
                                          "es-PR-KarinaNeural", "es-CU-ManuelNeural"], personajes
assert len(avisos) == 3 and avisos[0] == "No quedan más voces de Rep. Dominicana: Don Tito habla con la voz Víctor " \
                                         "(Puerto Rico).", avisos
assert all(p["voz"] in desde_prompt.voces().values() for p in personajes)  # serie._voz las acepta

print("Pruebas de calidad del contenido pasadas.")
