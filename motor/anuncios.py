"""Estudio de anuncios: de una foto de producto a varios anuncios realistas listos para Meta, TikTok y YouTube."""
import json
import shutil
import time
from pathlib import Path
from typing import Callable

from . import ia, memoria, seguro, video
from .desde_prompt import FALTAS, idioma_de, montar
from .idioma import t
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
            "escenas": {"type": "array", "items": {
                "type": "object",
                "properties": {"narracion": {"type": "string"}, "imagen": {"type": "string"}},
                "required": ["narracion", "imagen"], "additionalProperties": False}},
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
- Sin promesas falsas ni afirmaciones médicas o de ingresos que no se puedan probar. No inventes ofertas, precios ni
  descuentos: usa solo los que vengan en el pedido.
- texto_anuncio: el texto que va sobre el anuncio en Meta/TikTok, con emoji moderado y CTA."""


def crear(foto: str, producto: str, detalles: str, publico: str, oferta: str, estilo: str, formato: str = "9:16",
          voz: str = "es-DO-RamonaNeural", variantes: int = 3, segundos: int = 25,
          aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    foto = str(seguro.archivo_medio(foto, seguro.IMAGENES, t("foto del producto")))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-anuncio")
    carpeta.mkdir(parents=True)
    foto_local = Path(shutil.copy(foto, carpeta / f"producto{Path(foto).suffix.lower()}"))

    aviso(t("Investigando qué anuncios funcionan para este producto…"), 0.03)
    web = ia.investigar_web(
        f"Investiga en internet anuncios en video que estén funcionando ahora para productos como: {producto} "
        f"({detalles}). Público: {publico}. ¿Qué ganchos, ángulos, objeciones y formatos usan los anuncios ganadores "
        "en Meta Ads Library y TikTok Creative Center? Da ejemplos concretos.")

    aviso(t("La IA está creando las variantes del anuncio…"), 0.12)
    plan = ia.texto_json(INSTRUCCIONES, (
        f"Producto: {producto}\nDetalles: {detalles}\nPúblico: {publico}\nOferta y llamada a la acción: {oferta}\n"
        f"Estilo visual: {ESTILOS.get(estilo, estilo)}\nFormato: {formato}\nDuración: unos {segundos} s cada anuncio "
        f"(~{int(segundos * 2.5)} palabras, {max(3, round(segundos / 5))} escenas).\nVariantes: {variantes}"
        + idioma_de(voz)
        + (f"\n\nLo que está funcionando en el mercado (investigación en vivo):\n{web}" if web else "")
        + memoria.para("anuncios")), ESQUEMA)

    # La IA decide cuántas variantes y escenas devuelve: se recorta a lo pedido (el gasto no lo marca la IA).
    plan["variantes"] = plan["variantes"][:variantes]
    for v in plan["variantes"]:
        v["escenas"] = v["escenas"][:max(3, round(segundos / 5)) + 2]
        for e in v["escenas"]:  # y cada narración a 1-2 frases: la voz de pago se cobra por carácter
            e["narracion"] = e["narracion"][:400]
    resultados, total, notas = [], len(plan["variantes"]), []
    if not web:
        notas.append(t("Sin investigación en vivo: solo se hace con Claude conectado."))
    for k, v in enumerate(plan["variantes"], 1):
        desde = 0.15 + 0.83 * (k - 1) / total
        aviso(t("Anuncio {n} de {total}: «{angulo}»", n=k, total=total, angulo=v["angulo"]), desde)
        # respaldo: si falla una imagen y no hay ninguna anterior, se usa la foto del producto (nunca se cae el trabajo)
        # La foto solo va en las escenas que la piden («the product»; el estilo no cuenta): en un servicio, o en una
        # escena sin el producto, pegarla taparía la escena.
        notas_k = []
        montado = montar(v, carpeta, formato, voz, aviso, nombre=f"anuncio_{k}_base", desde=desde,
                         hasta=desde + 0.8 / total, respaldo=foto_local, notas=notas_k,
                         crear_imagen=lambda p, w, h, d: ia.imagen_con_producto(p, foto_local, w, h, d)
                         if "the product" in p.removesuffix(v["estilo_visual"]).lower() else ia.imagen(p, w, h, d))
        notas += [t("Anuncio {n}: {nota}", n=k, nota=nota) for nota in notas_k]
        archivo = video.cierre(montado, oferta or producto, formato, carpeta / f"anuncio_{k}.mp4") \
            if (oferta or producto).strip() else montado
        resultados.append({"archivo": str(archivo), "titulo": f"{k}. {v['angulo']} — {v['titulo']}",
                           "descripcion": t("Gancho: {gancho}\n\n{texto}", gancho=v["gancho"],
                                            texto=v["texto_anuncio"]),
                           "hashtags": v["hashtags"]})

    proyecto = {"tipo": "anuncio", "producto": producto, "formato": formato, "carpeta": str(carpeta),
                "titulo": t("Anuncios · {producto}", producto=producto), "resultados": resultados,
                "con_web": bool(web), "avisos": notas}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo! Con {n} aviso(s): los ves debajo del video.", n=len(notas)) if notas else t("¡Listo!"), 1.0)
    return proyecto
