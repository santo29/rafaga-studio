"""Estudio de anuncios: de una foto de producto a varios anuncios realistas listos para Meta, TikTok y YouTube."""
import json
import shutil
import time
import traceback
from pathlib import Path
from typing import Callable

from . import ia, memoria, nubes, seguro, video
from .desde_prompt import (ESCENA, FALTAS, MOVIMIENTO, idioma_codigo, idioma_de, montar, palabras_por_segundo,
                           relanzar_con_gasto)
from .idioma import IDIOMAS, t
from .shorts import PROYECTOS

ESTILOS = {
    "UGC testimonio (persona real con el móvil)": "UGC selfie-style smartphone video frames, real everyday people, "
        "natural light, authentic home settings, slightly imperfect handheld look, no studio",
    "Demostración del producto": "close-up hands using the product, clear before/after moments, clean real environment",
    "Lujo cinematográfico": "premium cinematic commercial, dramatic lighting, shallow depth of field, elegant sets",
    "Problema → solución": "first frames show the frustrating problem realistically, then the product solving it",
    "Oferta relámpago": "energetic retail ad look, bold colors, product hero shots, urgency",
}

ESQUEMA = {
    "type": "object",
    "properties": {"variantes": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "angulo": {"type": "string"}, "gancho": {"type": "string"}, "titulo": {"type": "string"},
            "texto_anuncio": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}},
            "estilo_visual": {"type": "string"},
            "escenas": {"type": "array", "items": ESCENA},  # con su movimiento y su texto en pantalla
        },
        "required": ["angulo", "gancho", "titulo", "texto_anuncio", "hashtags", "estilo_visual", "escenas"],
        "additionalProperties": False}}},
    "required": ["variantes"],
    "additionalProperties": False,
}

INSTRUCCIONES = """Eres el mejor estratega de anuncios de respuesta directa (Meta, TikTok, YouTube) y creativo de UGC.
Crea variantes de anuncio en video para pruebas A/B. Cada variante usa un ÁNGULO distinto (dolor, deseo, prueba
social, curiosidad, comparación, oferta…) y un GANCHO distinto en los primeros 2 segundos.
Estructura: gancho → problema o deseo → producto o servicio como solución → prueba/beneficio concreto → llamada a la
acción.
- """ + FALTAS + """
- Lo anunciado puede ser un producto o un negocio o servicio (barbería, restaurante, taller…): si es un servicio, se
  muestra el servicio y el local, no un «producto».
- narracion: frases cortas, habladas, naturales, como una persona real; en el idioma del pedido.
- imagen (en inglés): escena fotorrealista con personas y lugares reales, encuadre de móvil si el estilo es UGC. Si es
  un producto y sale en la escena, escribe exactamente "the product" (no inventes otra marca). La IA de imágenes lee
  cada descripción SOLA: nunca escribas «the same man», «he», «the guy»; repite la descripción completa de la persona
  (edad, cara, pelo, ropa) en cada escena donde salga. Sin texto, letreros ni logotipos escritos en la imagen.
""" + MOVIMIENTO + """
- Si te dan la foto del producto o del negocio, la ves: las escenas, los colores y el gancho encajan con lo que se ve.
- Sin promesas falsas ni afirmaciones médicas o de ingresos que no se puedan probar. No inventes ofertas, precios ni
  descuentos: usa solo los que vengan en el pedido.
- texto_anuncio: el texto que va sobre el anuncio en Meta/TikTok, con emoji moderado y CTA."""

# Con solo la foto (pasó: «hazme una versión de anuncio» con una foto acababa en preguntas), la IA que la ve dice qué
# se anuncia antes de investigar el mercado
VER_FOTO = """Miras la foto de lo que el usuario quiere anunciar. producto: su nombre corto (con la marca si se lee
en la foto) o el tipo de negocio (barbería, restaurante…). detalles: lo que se ve que ayuda a venderlo (qué es,
colores, envase, ambiente), en una frase. Nada inventado: ni precios ni ofertas. Si no ves ninguna foto, deja los dos
vacíos. Escribe en {idioma}."""
ESQUEMA_FOTO = {"type": "object", "properties": {"producto": {"type": "string"}, "detalles": {"type": "string"}},
                "required": ["producto", "detalles"], "additionalProperties": False}


def crear(foto: str, producto: str = "", detalles: str = "", publico: str = "", oferta: str = "",
          estilo: str = "UGC testimonio (persona real con el móvil)", formato: str = "9:16",
          voz: str = "es-DO-RamonaNeural", variantes: int = 3, segundos: int = 25,
          aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    """producto vacío: lo dice la IA de texto que ve la foto (si no la ve, el anuncio se hace igual con la foto)."""
    foto = str(seguro.archivo_medio(foto, seguro.IMAGENES, t("foto del producto")))
    pago = ia.video_de_pago()  # fijado al empezar: lo que se preguntó (ver desde_prompt.montar)
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-anuncio")
    carpeta.mkdir(parents=True)
    foto_local = Path(shutil.copy(foto, carpeta / f"producto{Path(foto).suffix.lower()}"))
    producto, detalles = str(producto or "").strip(), str(detalles or "").strip()
    if not producto and not isinstance(vista := ia.con_fotos("La foto:", [foto_local]), str):
        aviso(t("Mirando tu foto para saber qué anuncias…"), 0.02)
        try:
            visto = ia.texto_json(VER_FOTO.replace("{idioma}", IDIOMAS[idioma_codigo(voz)]), vista, ESQUEMA_FOTO,
                                  rapido=True)
            producto, detalles = visto["producto"].strip(), detalles or visto["detalles"].strip()
        except Exception:  # noqa: BLE001  sin eso el anuncio sale igual: el plan también ve la foto
            traceback.print_exc()

    web = None
    if producto:  # sin saber qué es, no hay mercado que investigar
        aviso(t("Investigando qué anuncios funcionan para este producto…"), 0.03)
        web = ia.investigar_web(
            f"Investiga en internet anuncios en video que estén funcionando ahora para productos como: {producto} "
            f"({detalles}). Público: {publico}. ¿Qué ganchos, ángulos, objeciones y formatos usan los anuncios "
            "ganadores en Meta Ads Library y TikTok Creative Center? Da ejemplos concretos.")

    aviso(t("La IA está creando las variantes del anuncio…"), 0.12)
    plan = ia.texto_json(INSTRUCCIONES, ia.con_fotos(
        f"Producto: {producto or 'el de la foto'}\nDetalles: {detalles}\nPúblico: {publico}\n"
        f"Oferta y llamada a la acción: {oferta}\n"
        f"Estilo visual: {ESTILOS.get(estilo, estilo)}\nFormato: {formato}\nDuración: unos {segundos} s cada anuncio "
        f"(~{int(segundos * palabras_por_segundo(voz))} palabras, {max(3, round(segundos / 5))} escenas)."
        f"\nVariantes: {variantes}"
        + idioma_de(voz)
        + (f"\n\nLo que está funcionando en el mercado (investigación en vivo):\n{web}" if web else "")
        + memoria.para("anuncios"), [foto_local]), ESQUEMA)

    # La IA decide cuántas variantes y escenas devuelve: se recorta a lo pedido (el gasto no lo marca la IA).
    plan["variantes"] = plan["variantes"][:variantes]
    for v in plan["variantes"]:
        v["escenas"] = v["escenas"][:max(3, round(segundos / 5)) + 2]
        for e in v["escenas"]:  # y cada narración a 1-2 frases: la voz de pago se cobra por carácter
            e["narracion"] = e["narracion"][:400]
    resultados, total, notas, pagados = [], len(plan["variantes"]), [], {"clips": 0}  # tope de clips de pago: del trabajo
    # La ortografía, antes de narrar y de quemar nada («FUSEL ESTE AROMA», el ángulo «Deseño», «#CaféBrise»)
    ia.repasar([x for v in plan["variantes"] for x in (v, *v["escenas"])],
               ("angulo", "titulo", "texto_anuncio", "hashtags", "narracion", "texto_pantalla"), idioma_codigo(voz),
               notas)
    if not web:
        notas.append(t("Sin investigación en vivo: solo se hace con Claude conectado."))

    def con_producto(p, w, h, d):
        """La escena del producto lleva siempre la foto real: con edición, pegada sobre una escena o, si no sale
        ninguna imagen, la foto sola (antes se repetía la escena anterior, sin el producto). Si falla la edición,
        imagen_con_producto ya pega la foto y lo dice una vez en notas_k."""
        try:
            return ia.imagen_con_producto(p, foto_local, w, h, d, avisos=notas_k)
        except Exception as error:  # noqa: BLE001  sin IA de imágenes que responda, o una edición que pudo cobrarse
            return foto_sola(error, d)  # sin llegar (no se paga otra imagen): la foto sola

    def nota(error, d, origen):
        causa = nubes._causa(error, "").replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
        notas_k.append(t("La imagen de la escena {n} no salió ({causa}). Se usó {origen}.",
                         n=int(d.stem.rsplit("_", 1)[1]) + 1, causa=causa, origen=origen))

    def foto_sola(error, d):
        nota(error, d, t("la foto de respaldo"))
        return foto_local

    for k, v in enumerate(plan["variantes"], 1):
        desde = 0.15 + 0.83 * (k - 1) / total
        aviso(t("Anuncio {n} de {total}: «{angulo}»", n=k, total=total, angulo=v["angulo"]), desde)
        # respaldo: si falla una imagen y no hay ninguna anterior, se usa la foto del producto (nunca se cae el trabajo)
        # La foto va en las escenas que la piden («the product»): en las demás, pegarla taparía la escena. Si la IA no
        # la pidió en ninguna (pasó con Groq: ningún anuncio enseñaba el producto), va en la del medio, la de la
        # solución; y siempre en el cierre.
        notas_k, escenas = [], v["escenas"]
        fotos = {i for i, e in enumerate(escenas) if "the product" in e["imagen"].lower()}
        if not fotos and escenas:
            medio = escenas[len(escenas) // 2]
            medio["imagen"] = f"the product as the hero of the shot, sharp and well lit, {medio['imagen']}"
            fotos = {len(escenas) // 2}
        try:
            montado = montar(v, carpeta, formato, voz, aviso, nombre=f"anuncio_{k}_base", desde=desde,
                             hasta=desde + 0.8 / total, respaldo=foto_local, notas=notas_k, pagados=pagados, pago=pago,
                             crear_imagen=lambda p, w, h, d, fotos=fotos: (
                                 con_producto if int(d.stem.rsplit("_", 1)[1]) in fotos else ia.imagen)(p, w, h, d))
            archivo = video.cierre(montado, oferta or producto, formato, carpeta / f"anuncio_{k}.mp4",
                                   producto=foto_local) if (oferta or producto).strip() else montado
        except Exception as error:  # lo ya pagado (también en las variantes anteriores) no se pierde de vista
            relanzar_con_gasto(error, notas + notas_k, carpeta)
        notas += [t("Anuncio {n}: {nota}", n=k, nota=nota) for nota in notas_k]
        resultados.append({"archivo": str(archivo), "titulo": f"{k}. {v['angulo']} — {v['titulo']}",
                           # Solo el texto del anuncio: es lo que se copia y se publica, y el gancho ya se dice en el
                           # video (con la etiqueta interna «Gancho:» delante se publicaba tal cual)
                           "descripcion": v["texto_anuncio"],
                           "hashtags": v["hashtags"]})

    proyecto = {"tipo": "anuncio", "producto": producto, "formato": formato, "carpeta": str(carpeta),
                "titulo": t("Anuncios · {producto}", producto=producto or Path(foto).stem), "resultados": resultados,
                "con_web": bool(web), "avisos": notas}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo! Hay avisos ({n}): los ves debajo del video.", n=len(notas)) if notas else t("¡Listo!"), 1.0)
    return proyecto
