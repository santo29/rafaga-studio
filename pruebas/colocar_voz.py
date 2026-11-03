"""La voz puesta sola en su punto, sin red ni claves: frases, cortes reales con ffmpeg, lo que dice la IA comprobado por el
código, las fotos solo si puede mandarlas, tiempos sin pisar lo que se oye y nada narrado dos veces.
python -m pruebas.colocar_voz"""
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = "http://127.0.0.1:9"  # nada de red: ni por descuido
from PySide6.QtGui import QColor, QImage  # noqa: E402

from motor import claves, colocar_voz as cv, desde_prompt, diseno, edicion, ia, render_edicion, video  # noqa: E402

diseno.asegurar_qt()
tmp = Path(tempfile.mkdtemp(prefix="rafaga-colocar-voz-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # nunca las claves del usuario
GRATIS = "es-DO-EmilioNeural"


def falla(funcion, *args, error=ValueError, **kw) -> str:
    try:
        funcion(*args, **kw)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar: {getattr(funcion, '__name__', funcion)}")


def video_de_colores(nombre, colores, segundos=2, sonido=False) -> str:
    """Un video con un corte seco en cada cambio de color."""
    ruta = tmp / nombre
    entradas, cadena = [], ""
    for i, color in enumerate(colores):
        entradas += ["-f", "lavfi", "-i", f"color={color}:s=160x284:d={segundos}:r=10"]
        cadena += f"[{i}]"
    if sonido:
        entradas += ["-f", "lavfi", "-i", f"sine=frequency=400:duration={segundos * len(colores)}"]
    video.ffmpeg(*entradas, "-filter_complex", f"{cadena}concat=n={len(colores)}:v=1[v]", "-map", "[v]",
                 *(["-map", f"{len(colores)}:a"] if sonido else []), "-pix_fmt", "yuv420p", ruta)
    return str(ruta)


def foto(nombre, color) -> str:
    ruta, imagen = tmp / nombre, QImage(90, 160, QImage.Format_RGB32)
    imagen.fill(QColor(color))
    imagen.save(str(ruta))
    return str(ruta)


def proyecto(*rutas):
    p = edicion.nuevo("Prueba", "9:16")
    for ruta in rutas:
        p = edicion.anadir_medio(p, ruta)
    return p


narradas, recargado = [], False


def narrar(texto, voz, destino, velocidad=1.0):
    """Medio segundo por palabra, sin red."""
    narradas.append((texto, voz, velocidad))
    if texto.startswith("FALLA") and not recargado:
        raise RuntimeError("sin saldo")
    video.ffmpeg("-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", 0.5 * len(texto.split()) / velocidad,
                 "-c:a", "libmp3lame", destino)
    return []


pedidos = []


def ia_que_dice(*escenas_dichas):
    def responder(instrucciones, pedido, esquema, rapido=False, solo_elegida=False):
        pedidos.append(pedido)
        assert esquema is cv.ESQUEMA and rapido and solo_elegida
        return {"colocacion": [{"frase": i, "escena": e} for i, e in enumerate(escenas_dichas, 1)]}
    return responder


reales = desde_prompt.narrar, ia.texto_json, ia.ve_fotos, render_edicion.subtitulos_automaticos
desde_prompt.narrar = narrar
ia.ve_fotos = lambda uso="texto": False
render_edicion.subtitulos_automaticos = lambda p, c, aviso=None: (_ for _ in ()).throw(AssertionError("no debió transcribir"))
carpeta = tmp / "proyecto"
carpeta.mkdir()

try:
    # ---------- Las frases ----------
    assert cv.frases("Hola a todos. ¿Cómo están hoy? ¡Muy bien todos!") == ["Hola a todos.", "¿Cómo están hoy?", "¡Muy bien todos!"]
    assert cv.frases("Primera línea sin punto\nSegunda línea sin punto") == ["Primera línea sin punto", "Segunda línea sin punto"]
    assert cv.frases("Sr. Pérez llegó tarde hoy. Y se fue.") == ["Sr. Pérez llegó tarde hoy.", "Y se fue."]
    assert cv.frases("«Dijo que no.» Luego se fue lejos.") == ["«Dijo que no.»", "Luego se fue lejos."]
    # Un punto que no acaba la frase, no la parte
    assert cv.frases("Visítanos en la Av. Duarte, abierto de 9 a.m. a 5 p.m. todos los días.") == [
        "Visítanos en la Av. Duarte, abierto de 9 a.m. a 5 p.m. todos los días."]
    assert cv.frases("Hoy vino el Sr. Pérez a casa. Yo no estaba.") == ["Hoy vino el Sr. Pérez a casa.", "Yo no estaba."]
    assert cv.frases("« Bonjour à tous ! » dit-il ce matin.") == ["« Bonjour à tous ! » dit-il ce matin."]
    assert cv.frases("todo en minúscula aquí va\ny esta otra línea también") == ["todo en minúscula aquí va", "y esta otra línea también"]
    assert cv.frases("") == [] and cv.frases("   \n  ") == [] and cv.frases(None) == []
    # Con un tope, nada se pierde: lo que sobra va en la última
    muchas = " ".join(f"Esta es la frase {n}." for n in range(1, 7))
    assert len(cv.frases(muchas, 3)) == 3 and cv.frases(muchas, 3)[-1].endswith("frase 6.") and "frase 3." in cv.frases(muchas, 3)[-1]

    # ---------- Las escenas: fotos y cortes reales ----------
    colores = video_de_colores("colores.mp4", ["red", "blue", "green"])
    p = proyecto(colores)
    lista = cv.escenas(p)
    assert [round(e["inicio"]) for e in lista] == [0, 2, 4] and round(lista[-1]["fin"]) == 6, lista
    p = proyecto(foto("a.png", "#FF0000"), foto("b.png", "#00FF00"))
    assert [(e["inicio"], e["fin"]) for e in cv.escenas(p)] == [(0, 3), (3, 6)]  # cada foto, su escena
    # Un tramo recortado y a otra velocidad: los cortes, en tiempos de la línea
    p = proyecto(video_de_colores("colores4.mp4", ["red", "blue", "green"], 4))
    p["clips"][0].update(desde=1, hasta=11, velocidad=2)
    p = edicion.validar(p)  # cortes a 4 y 8 s del original: 3 y 7 s del tramo, 1,5 y 3,5 s en la línea
    assert [round(e["inicio"], 1) for e in cv.escenas(p)] == [0, 1.5, 3.5] and cv.escenas(p)[-1]["fin"] == 5, cv.escenas(p)
    # Un plano largo sin cortes se mira por tramos
    largo = video_de_colores("largo.mp4", ["red"], 30)
    assert len(cv.escenas(proyecto(largo))) == 3
    # Muy cortas: se unen. Y nunca más que las que caben en las fotos
    p = proyecto(foto("a.png", "#FF0000"))
    p["clips"][0]["hasta"] = 0.4
    p = edicion.anadir_medio(p, foto("b.png", "#00FF00"))
    assert len(cv.escenas(p)) == 1
    p = edicion.nuevo("Muchas", "9:16")
    for n in range(40):
        p = edicion.anadir_medio(p, foto(f"m{n}.png", "#112233"))
    assert len(cv.escenas(p)) == cv.MAX_ESCENAS == 24
    # Un montaje rápido, con un plano cada 0,8 s, sigue siendo muchas escenas: no una sola de un minuto
    cada_08 = [i * 0.8 for i in range(1, 75)]
    real_cortes = cv._cortes
    cv._cortes = lambda clip: cada_08
    rapido = proyecto(video_de_colores("rapido.mp4", ["red"], segundos=60))
    lista = cv.escenas(rapido)
    cv._cortes = real_cortes
    assert len(lista) == cv.MAX_ESCENAS and lista[-1]["fin"] == 60 and all(e["fin"] - e["inicio"] < 10 for e in lista), lista
    assert cv.escenas(p)[0]["inicio"] == 0 and cv.escenas(p)[-1]["fin"] == 120

    # ---------- Sin IA que vea ni sonido: en orden, repartidas, y lo dice ----------
    def sin_llamar(*a, **k):
        raise AssertionError("sin nada que comparar no se gasta en preguntar")
    ia.texto_json = sin_llamar
    p = proyecto(foto("a.png", "#FF0000"), foto("b.png", "#00FF00"), foto("c.png", "#0000FF"))
    r = cv.colocar(p, "Una frase de cuatro palabras. Otra frase de cuatro palabras. La última de cuatro palabras.", GRATIS, carpeta)
    assert [f["escena"] for f in r["frases"]] == [1, 2, 3] and [a["inicio"] for a in r["audios"]] == [0.15, 3.15, 6.15], r
    assert any("repartidas" in n for n in r["notas"]) and all(a["tipo"] == "voz" for a in r["audios"])
    limpio = edicion.validar({**p, "audios": [{**a, "id": None} for a in r["audios"]]})  # el proyecto las acepta
    assert [a["tipo"] for a in limpio["audios"]] == ["voz"] * 3

    # ---------- La IA decide; el código comprueba y pone los tiempos ----------
    narradas.clear()
    p = proyecto(colores)
    ia.ve_fotos = lambda uso="texto": True
    ia.texto_json = ia_que_dice(2, 3)
    r = cv.colocar(p, "Esto va azul. Esto va verde.", GRATIS, carpeta)
    assert [f["escena"] for f in r["frases"]] == [2, 3] and [a["inicio"] for a in r["audios"]] == [2.15, 4.15], r
    assert len(narradas) == 2 and all(n[1] == GRATIS and n[2] == 1 for n in narradas)
    assert not r["notas"], r["notas"]
    # Las fotos van numeradas en una hoja, como imagen, y solo se manda eso
    bloques = pedidos[-1]
    assert isinstance(bloques, list) and sum(b["type"] == "image" for b in bloques) == 1
    assert "1. De 0.0 a 2.0 s" in bloques[0]["text"] and "1. (1.5 s) Esto va azul." in bloques[0]["text"]
    # Sin permiso para mandar fotos: ninguna. Sin sonido tampoco hay qué comparar: no se pregunta a la IA
    pedidos.clear()
    r = cv.colocar(p, "Una frase de cuatro palabras.", GRATIS, carpeta, fotos=False)
    assert not pedidos and any("repartidas" in n for n in r["notas"])
    # Una IA que no ve fotos: tampoco se le hacen
    ia.ve_fotos = lambda uso="texto": False
    r = cv.colocar(p, "Una frase de cuatro palabras.", GRATIS, carpeta)
    assert not pedidos
    ia.ve_fotos = lambda uso="texto": True

    # Lo que dice la IA son datos: fuera de rango, de otro tipo o desordenado no rompe nada
    frases_dos = "Primera frase de la voz. Segunda frase de la voz."
    # Un número equivocado afecta solo a su frase
    assert cv._de_la_ia({"colocacion": [{"frase": i, "escena": e} for i, e in enumerate([10, 2, 3, 4, 5, 6], 1)]},
                        [0, 1, 3, 5, 6, 8], 10) == [0, 1, 2, 3, 4, 5]
    for dicho, esperado in (([3, 1], [3, 3]),  # en orden siempre
                            ([9, 2], [1, 2]),  # la escena 9 no existe: la frase va donde caería al repartir
                            ([0, -1], None),  # nada válido: repartidas
                            (["2", 2.5], None), ([True, False], None)):
        ia.texto_json = ia_que_dice(*dicho)
        r = cv.colocar(p, frases_dos, GRATIS, carpeta)
        if esperado:
            assert [f["escena"] for f in r["frases"]] == esperado, (dicho, r["frases"])
        else:
            assert any("no dijo dónde" in n for n in r["notas"]), (dicho, r["notas"])
    for rara in (None, {}, {"colocacion": "x"}, {"colocacion": [1, "a", None, {}]}):
        ia.texto_json = lambda *a, **k: rara
        assert any("no dijo dónde" in n for n in cv.colocar(p, "Una frase de la voz.", GRATIS, carpeta)["notas"])
    # La IA falla: la voz se coloca igual y se dice por qué
    ia.texto_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin cuota"))
    r = cv.colocar(p, "Una frase de la voz.", GRATIS, carpeta)
    assert len(r["audios"]) == 1 and any("No pude preguntarle a tu IA (sin cuota)" in n for n in r["notas"]), r["notas"]

    # ---------- Lo que ya se oye: se le dice a la IA y no se pisa ----------
    con_sonido = video_de_colores("sonido.mp4", ["red", "blue"], 3, sonido=True)
    p = proyecto(con_sonido)
    oidas = [{"palabra": "hola", "inicio": 3.0, "fin": 3.4}, {"palabra": "gente", "inicio": 3.5, "fin": 4.0}]
    render_edicion.subtitulos_automaticos = lambda proyecto_, c, aviso=None: oidas
    ia.ve_fotos = lambda uso="texto": False
    pedidos.clear()
    ia.texto_json = ia_que_dice(2)
    r = cv.colocar(p, "Voz muy corta.", GRATIS, carpeta)
    assert "Se oye: «hola gente»" in pedidos[-1] and isinstance(pedidos[-1], str)
    assert r["audios"][0]["inicio"] >= 4.0 and not r["notas"], r  # empieza después de lo que se oye
    # Sin hueco en su escena: se queda en su sitio y lo dice
    ia.texto_json = ia_que_dice(2)
    oidas[1]["fin"] = 5.95
    r = cv.colocar(p, "Una frase un poco larga para este hueco.", GRATIS, carpeta)
    assert round(r["audios"][0]["inicio"], 2) == 3.15 and any("encima de lo que ya se oye" in n for n in r["notas"]), r
    # Sin permiso, a la IA no le llega lo que se oye: los subtítulos solo sirven para no hablar encima
    con_subtitulos = proyecto(con_sonido)
    con_subtitulos["subtitulos"]["palabras"] = [{"palabra": "secreto", "inicio": 0.2, "fin": 0.8}]
    con_subtitulos = edicion.validar(con_subtitulos)
    render_edicion.subtitulos_automaticos = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debió transcribir"))
    pedidos.clear()
    ia.ve_fotos = lambda uso="texto": True
    r = cv.colocar(con_subtitulos, "Voz muy corta.", GRATIS, carpeta, fotos=False, oir=False)
    assert not pedidos and r["audios"][0]["inicio"] >= 0.8, r  # ni se pregunta a la IA, y no habla encima
    ia.ve_fotos = lambda uso="texto": False
    # Dos frases en la misma escena buscan su hueco en ella, no se quedan encima de lo que se oye
    lista = [{"inicio": 0.0, "fin": 11.0}]
    assert cv._colocar_en_tiempo([2, 2], [0, 0], lista, [(0.0, 3.0)]) == [3.25, 5.5]
    # Sin permiso para oír, no se transcribe nada; los subtítulos que ya hay sí valen
    render_edicion.subtitulos_automaticos = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debió transcribir"))
    assert cv._oido(proyecto(con_sonido), carpeta, False, lambda *a: None) == []
    # Un video mudo no se transcribe, y los subtítulos que ya tenga se aprovechan
    render_edicion.subtitulos_automaticos = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debió transcribir"))
    assert not cv._suena(proyecto(colores)) and cv._suena(proyecto(con_sonido))
    p = proyecto(con_sonido)
    p["subtitulos"]["palabras"] = [{"palabra": "ya", "inicio": 0.2, "fin": 0.6}]
    p = edicion.validar(p)
    ia.texto_json = ia_que_dice(1)
    r = cv.colocar(p, "Una voz de dos segundos ya.", GRATIS, carpeta)
    assert r["audios"][0]["inicio"] >= 0.6, r
    # Con el sonido apagado o sin poder transcribir, sigue
    p = proyecto(con_sonido)
    p["clips"][0]["silencio"] = True
    assert not cv._suena(edicion.validar(p))
    render_edicion.subtitulos_automaticos = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin Whisper"))
    assert cv._oido(proyecto(con_sonido), carpeta, True, lambda *a: None) == []
    # Una toma de «Grabarte» puesta como capa también suena
    p = proyecto(foto("a.png", "#FF0000"))
    assert not cv._suena(p)
    p["capas"] = [{"tipo": "video", "archivo": con_sonido, "silencio": False, "volumen": 1}]
    assert cv._suena(p)
    p["capas"][0]["silencio"] = True
    assert not cv._suena(p)
    # Las voces ya puestas tampoco se pisan
    p = proyecto(foto("a.png", "#FF0000"), foto("b.png", "#00FF00"))
    r = cv.colocar(p, "Una voz de dos segundos ya.", GRATIS, carpeta)
    p = edicion.validar({**p, "audios": [{**a, "id": None} for a in r["audios"]]})
    assert cv._ocupado(p, [{"palabra": "x", "inicio": 2.3, "fin": 2.5}])[0][0] == 0.15

    # ---------- Tiempo: en orden, sin encimarse, y lo que no cabe se dice ----------
    render_edicion.subtitulos_automaticos = reales[3]
    ia.ve_fotos = lambda uso="texto": False
    p = proyecto(foto("a.png", "#FF0000"), foto("b.png", "#00FF00"))
    narradas.clear()
    r = cv.colocar(p, "Esta frase tiene ocho palabras en total aquí. Otra frase.", GRATIS, carpeta)
    inicios = [a["inicio"] for a in r["audios"]]
    assert inicios[1] >= inicios[0] + r["audios"][0]["duracion_archivo"]  # nunca una encima de otra
    # Más voz que video: un poco más rápida (hasta un 20 %), antes de narrar: una sola vez cada frase
    narradas.clear()
    texto = " ".join(f"Palabra {n} de esta larga frase." for n in range(4))
    r = cv.colocar(p, texto, GRATIS, carpeta)
    assert len(narradas) == 4 and all(n[2] == 1.2 for n in narradas), narradas
    assert any("más rápida" in n for n in r["notas"]) and any("después que el video" in n for n in r["notas"]), r["notas"]
    # Cabe bien: a su velocidad
    narradas.clear()
    r = cv.colocar(p, "Una frase corta aquí.", GRATIS, carpeta)
    assert narradas[-1][2] == 1 and not any("más rápida" in n for n in r["notas"])

    # ---------- Si la narración falla a mitad, lo ya hecho se conserva y se dice ----------
    narradas.clear()
    a_medias = "Esta frase sale bien. Esta también sale. FALLA aquí la voz. Y esta ni se intenta."
    r = cv.colocar(p, a_medias, GRATIS, carpeta)
    assert len(r["audios"]) == 2 and len(r["frases"]) == 2 and any(
        "2 frases se quedaron sin voz, desde «FALLA aquí la voz.»: sin saldo" in n for n in r["notas"]), r
    assert len(narradas) == 3  # no siguió gastando
    # Repetir tras ese fallo: las que ya están en el video ni se narran ni suenan dobles
    pasadas = edicion.validar({**p, "audios": [{**a, "id": None} for a in r["audios"]]})
    narradas.clear()
    recargado = True
    otra = cv.colocar(pasadas, a_medias, GRATIS, carpeta)
    assert [n[0] for n in narradas] == ["FALLA aquí la voz.", "Y esta ni se intenta."] and len(otra["audios"]) == 2, narradas
    pisa = any(x["inicio"] < y["inicio"] + y["hasta"] and y["inicio"] < x["inicio"] + x["hasta"]
               for x in otra["audios"] for y in r["audios"])
    assert not pisa or any("encima de lo que ya se oye" in n for n in otra["notas"]), otra  # encima de las puestas, solo si lo dice
    pasadas = edicion.validar({**pasadas, "audios": [*pasadas["audios"], *({**a, "id": None} for a in otra["audios"])]})
    narradas.clear()
    igual = cv.colocar(pasadas, a_medias, GRATIS, carpeta)
    assert not narradas and igual["audios"] == [] and igual["notas"][-1] == "Esas frases ya están en el video.", igual
    recargado = False
    # Con ElevenLabs, lo ya pagado se reutiliza aunque se haya quitado del video (Deshacer), y la cifra solo cuenta lo que falta
    claves.guardar({"proveedor": "elevenlabs", "clave": "sk_" + "a1" * 24, "usos": ["voz"], "modelo_voz": "m",
                    "voces": [{"id": "bella", "nombre": "Bella", "acento": ""}]})
    BELLA = "eleven:bella"
    narradas.clear()
    p_e = proyecto(foto("a.png", "#FF0000"), foto("b.png", "#00FF00"), foto("c.png", "#0000FF"))
    texto_e = "Primera frase de pago. Segunda frase de pago."
    assert cv.letras_por_pagar(p_e, texto_e, BELLA, carpeta) == len(texto_e) - 1
    cv.colocar(p_e, "Primera frase de pago.", BELLA, carpeta)
    assert len(narradas) == 1
    assert cv.letras_por_pagar(p_e, texto_e, BELLA, carpeta) == len("Segunda frase de pago.")
    r_e = cv.colocar(p_e, texto_e, BELLA, carpeta)
    assert len(narradas) == 2 and [n[0] for n in narradas] == ["Primera frase de pago.", "Segunda frase de pago."], narradas
    assert len(r_e["audios"]) == 2 and cv.letras_por_pagar(p_e, texto_e, BELLA, carpeta) == 0
    # Terminar con la voz gratis lo que faltó: las ya puestas no se repiten, por lo que dicen y no por su voz
    con_eleven = edicion.validar({**p_e, "audios": [{**r_e["audios"][0], "id": None}]})
    narradas.clear()
    r_g = cv.colocar(con_eleven, texto_e, GRATIS, carpeta)
    assert [n[0] for n in narradas] == ["Segunda frase de pago."] and any("1 frases ya estaban" in n for n in r_g["notas"]), r_g
    # El tope de audios no cambia cómo se parte el texto: lo ya pagado se sigue reconociendo
    assert cv.frases(texto_e, cv.MAX_FRASES) == ["Primera frase de pago.", "Segunda frase de pago."]
    musicas = [{"tipo": "musica", "archivo": r_e["audios"][0]["archivo"], "hasta": 1, "duracion_archivo": 1, "inicio": 0}]
    casi_lleno = edicion.validar({**p_e, "audios": musicas * (edicion.MAX_AUDIOS - 1)})
    assert cv._pendientes(casi_lleno, texto_e, BELLA)[0] == [texto_e]  # solo si no caben se unen
    claves.borrar("elevenlabs")
    # Un audio ilegible sin ninguno bueno: se dice el motivo real
    medir_real, edicion._medir = edicion._medir, lambda r: (_ for _ in ()).throw(ValueError("audio roto"))
    assert "audio roto" in falla(cv.colocar, p, "Una frase de la voz.", GRATIS, carpeta)
    edicion._medir = medir_real
    # Al cerrar la app no sigue narrando (ni cobrando) lo que nadie verá
    narradas.clear()
    render_edicion._cerrando.set()
    assert "cerrando" in falla(cv.colocar, p, "Una frase de la voz.", GRATIS, carpeta, error=RuntimeError) and not narradas
    render_edicion._cerrando.clear()
    # Lo que no cabe en los 60 minutos no se paga ni rompe el proyecto
    largo_p = proyecto(foto("a.png", "#FF0000"))
    largo_p["clips"][0]["hasta"] = edicion.MAX_DURACION - 2
    largo_p = edicion.validar(largo_p)
    narradas.clear()
    ia.texto_json = ia_que_dice(1, 1, 1)
    r_l = cv.colocar(largo_p, "Una frase con varias palabras de voz. Otra frase con varias palabras de voz.", GRATIS, carpeta)
    edicion.validar({**largo_p, "audios": [{**a, "id": None} for a in r_l["audios"]]})
    # Tampoco si la voz real dura más de lo calculado: se corta en el límite y se dice
    largo_p["clips"][0]["hasta"] = edicion.MAX_DURACION - 4
    largo_p = edicion.anadir_medio(edicion.validar(largo_p), foto("b.png", "#00FF00"))
    estimado_real, desde_prompt.palabras_por_segundo = desde_prompt.palabras_por_segundo, lambda voz: 100
    tiempo_real, cv._colocar_en_tiempo = cv._colocar_en_tiempo, lambda d, e, l, o: [edicion.MAX_DURACION - 2.0] * len(d)
    narradas.clear()
    r_l = cv.colocar(largo_p, "Una frase con varias palabras de voz que acaba tarde.", GRATIS, carpeta)
    desde_prompt.palabras_por_segundo, cv._colocar_en_tiempo = estimado_real, tiempo_real
    final = edicion.validar({**largo_p, "audios": [{**a, "id": None} for a in r_l["audios"]]})
    assert edicion.duracion_total(final) <= edicion.MAX_DURACION and any("límite de 60 minutos" in n for n in r_l["notas"]), r_l
    assert "sin saldo" in falla(cv.colocar, p, "FALLA desde el principio.", GRATIS, carpeta, error=RuntimeError)

    # ---------- Lo que no se puede ----------
    assert "Añade primero" in falla(cv.colocar, edicion.nuevo("Vacío", "9:16"), "Hola", GRATIS, carpeta)
    assert "Escribe" in falla(cv.colocar, p, "   ", GRATIS, carpeta)
    assert "no existe" in falla(cv.colocar, p, "Una frase de la voz.", "eleven:../../hack", carpeta)  # la lista de siempre
    lleno = edicion.validar({**p, "audios": [{"tipo": "musica", "archivo": str(r["audios"][0]["archivo"]), "hasta": 1,
                                              "duracion_archivo": 1, "inicio": 0}] * edicion.MAX_AUDIOS})
    assert "máximo de audios" in falla(cv.colocar, lleno, "Una frase de la voz.", GRATIS, carpeta)
    casi = edicion.validar({**p, "audios": lleno["audios"][:edicion.MAX_AUDIOS - 1]})
    r = cv.colocar(casi, "Una frase de la voz. Otra frase de la voz.", GRATIS, carpeta)
    assert len(r["audios"]) == 1 and "Otra frase" in r["frases"][0]["texto"]  # cabe uno: las dos juntas

    # Las hojas de fotos: se borran al terminar y llevan cada escena
    p = proyecto(colores)
    with tempfile.TemporaryDirectory() as t_:
        hojas = cv._mosaicos(p, carpeta, cv.escenas(p), Path(t_), lambda *a: None)
        assert len(hojas) == 1 and QImage(str(hojas[0])).width() == 768
        hoja = QImage(str(hojas[0]))
        # El color de cada escena, en su cuadro (el rojo arriba a la izquierda, el azul en medio, el verde a la derecha)
        assert hoja.pixelColor(128, 200).red() > 200 and hoja.pixelColor(384, 200).blue() > 200
        assert hoja.pixelColor(640, 200).green() > 80
    assert json.dumps(cv.ESQUEMA)  # se manda tal cual

    # ---------- El botón del editor: pregunta lo que toca, todo en un solo «deshacer» ----------
    from PySide6.QtWidgets import QApplication, QMessageBox
    import time
    import ui.paginas.edicion as pe
    app = QApplication.instance() or QApplication(["pruebas"])
    avisados, preguntas = [], []
    QMessageBox.exec = lambda caja: avisados.append(caja.text()) or QMessageBox.Ok
    respuesta = {"fotos": QMessageBox.No}
    QMessageBox.question = staticmethod(lambda padre, titulo, texto, *a: preguntas.append(texto) or respuesta["fotos"])
    pagina = pe.PaginaEdicion()

    def esperar_tareas():
        fin = time.monotonic() + 60
        while pagina.tareas and time.monotonic() < fin:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        assert not pagina.tareas

    claves.borrar("elevenlabs")
    # Sin texto o sin video lo dice, sin gastar nada
    narradas.clear()
    pagina.voz_en_escenas()
    assert "Escribe lo que dirá la voz." in avisados[-1]
    pagina.texto_voz.setPlainText("Una frase de la voz.")
    pagina.voz_en_escenas()
    assert "Añade primero" in avisados[-1] and not narradas

    pagina.proyecto = proyecto(colores)
    pagina.carpeta = carpeta
    pagina.texto_voz.setPlainText("Esto va azul. Esto va verde.")
    ia.ve_fotos = lambda uso="texto": False
    ia.texto_json = ia_que_dice(2, 3)
    respuesta["fotos"] = QMessageBox.Yes
    pedidos.clear()
    pagina.voz_en_escenas()
    esperar_tareas()
    voces = [a for a in pagina.proyecto["audios"] if a["tipo"] == "voz"]
    # Con una IA que no ve fotos no se le pide permiso ni se le mandan; sin sonido, no se le pregunta
    assert not preguntas and len(voces) == 2, (preguntas, voces)
    pagina.deshacer()
    assert not pagina.proyecto["audios"]  # las dos, de una vez

    # Con una IA que ve fotos pide permiso en cada trabajo; con «No», ninguna foto y la voz sale igual
    claves.guardar({"proveedor": "gemini", "clave": "AIza" + "a" * 35, "usos": ["texto"]})
    ia.ve_fotos = lambda uso="texto": True
    respuesta["fotos"] = QMessageBox.No
    pagina.voz_en_escenas()
    esperar_tareas()
    assert len(preguntas) == 1 and "fotos pequeñas del video a Gemini" in preguntas[0] and "¿Lo mando?" in preguntas[0]
    assert "sonido" not in preguntas[0]  # este video no suena: de eso no se pregunta
    assert len([a for a in pagina.proyecto["audios"] if a["tipo"] == "voz"]) == 2
    assert not pedidos  # sin fotos ni sonido no hay nada que preguntarle a la IA
    pagina.deshacer()
    respuesta["fotos"] = QMessageBox.Yes
    pagina.voz_en_escenas()
    esperar_tareas()
    assert len(preguntas) == 2 and "fotos_voz" not in claves.ajustes()
    assert isinstance(pedidos[-1], list) and sum(b["type"] == "image" for b in pedidos[-1]) == 1
    voces = [a for a in pagina.proyecto["audios"] if a["tipo"] == "voz"]
    assert [round(a["inicio"], 2) for a in voces] == [2.15, 4.15], voces
    assert pagina.sel == voces[0]["id"] and "Frases colocadas: 2." in pagina.estado.text()
    pagina.deshacer()
    pagina.voz_en_escenas()
    esperar_tareas()
    assert len(preguntas) == 3  # cada video es distinto: se pregunta en cada trabajo
    pagina.deshacer()
    # Su sonido solo sale con permiso, y si cuesta lo dice: con «No», ni transcribe ni manda fotos
    sonando = proyecto(con_sonido)
    sonando["subtitulos"]["palabras"] = []
    pagina.proyecto = edicion.validar(sonando)
    claves.guardar({"proveedor": "openai", "clave": "sk-" + "a" * 40, "usos": ["texto", "imagen", "transcripcion"]})
    para_real = claves.para
    claves.para = lambda uso: {"proveedor": "openai", "clave": "sk-x"} if uso == "transcripcion" else para_real(uso)
    transcritos = []
    render_edicion.subtitulos_automaticos = lambda *a, **k: transcritos.append(1) or []
    ia.ve_fotos = lambda uso="texto": False
    respuesta["fotos"] = QMessageBox.No
    preguntas.clear()
    pagina.voz_en_escenas()
    esperar_tareas()
    assert len(preguntas) == 1 and "Su sonido a OpenAI, por unos" in preguntas[0] and not transcritos, preguntas
    assert "Lo que se dice en el video, en texto, a" in preguntas[0]
    pagina.deshacer()
    respuesta["fotos"] = QMessageBox.Yes
    pagina.voz_en_escenas()
    esperar_tareas()
    assert transcritos
    claves.para = para_real
    render_edicion.subtitulos_automaticos = reales[3]
    pagina.deshacer()
    pagina.proyecto = proyecto(colores)
    # Si abrió otro video mientras trabajaba, las voces no entran en ese
    pagina.texto_voz.setPlainText("Esto va azul.")
    otra_carpeta = tmp / "otro"
    otra_carpeta.mkdir()
    ia.texto_json = ia_que_dice(1)
    pagina.voz_en_escenas()
    pagina.carpeta = otra_carpeta
    esperar_tareas()
    assert not [a for a in pagina.proyecto["audios"] if a["tipo"] == "voz"] and "no añadí las voces" in avisados[-1], avisados
    pagina.carpeta = carpeta
    pagina.texto_voz.setPlainText("Esto va azul. Esto va verde.")
    ia.texto_json = ia_que_dice(2, 3)
    pagina.voz_en_escenas()
    esperar_tareas()
    # Las notas se enseñan al terminar
    avisados.clear()
    pagina.deshacer()
    pagina.texto_voz.setPlainText(" ".join(f"Palabra {n} de esta larga frase." for n in range(9)))
    ia.texto_json = ia_que_dice(1)
    pagina.voz_en_escenas()
    esperar_tareas()
    assert any("después que el video" in a for a in avisados), avisados
finally:
    desde_prompt.narrar, ia.texto_json, ia.ve_fotos, render_edicion.subtitulos_automaticos = reales

print("Pruebas de la voz colocada pasadas.")
