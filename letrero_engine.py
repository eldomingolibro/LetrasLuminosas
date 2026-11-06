#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor del "Letrero luminoso" (channel / lightbox letters) con TAPA ENCASTRADA.

Cada letra son DOS piezas:
  - CAJA (opaca): fondo cerrado + paredes con la forma de la letra, HUECA por dentro
    (hueco para la tira LED). En la boca lleva un ENCASTRE (rebaje/escalón) donde
    apoya y encaja la tapa.
  - TAPA (translúcida/blanca): plaquita con la forma de la letra que entra en el
    encastre con holgura y queda enrasada; difunde la luz del LED.
Opción con o sin tapa, y con o sin placa trasera que une todas las letras.

Reutiliza helpers de texto de placa_engine.

Salidas:
  build(p)         -> Trimesh (caja + tapa juntas, para STL)
  build_scene(p)   -> Scene con 2 cuerpos de color (caja opaca + tapa translúcida) para 3MF
  build_preview(p) -> piezas {name, v, f, color, glow} para el visor
"""
import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.affinity import translate

import placa_engine as pe


def _concat(ms):
    ms = [m for m in ms if m is not None and len(m.faces)]
    if not ms:
        return None
    return trimesh.util.concatenate(ms) if len(ms) > 1 else ms[0]


def _ancho_hueco(polys, gp):
    """Ancho del hueco interior (canal del LED) = diámetro del mayor círculo que
    cabe en la cavidad (poly erosionada por la pared gp). Devuelve el canal más
    ancho entre todas las letras, en mm (donde mejor entra la tira de LED)."""
    best = 0.0
    for poly in polys:
        for c in pe._to_polys(poly.buffer(-gp)):
            if c.area < 1e-6:
                continue
            b = c.bounds
            lo, hi = 0.0, 0.5 * min(b[2] - b[0], b[3] - b[1])
            for _ in range(16):                       # búsqueda binaria del radio
                mid = (lo + hi) / 2.0
                if not c.buffer(-mid).is_empty:
                    lo = mid
                else:
                    hi = mid
            best = max(best, 2.0 * lo)
    return best


def _ext(poly, h, z0=0.0):
    """Extruye un Polygon/MultiPolygon en Z por h, apoyado en z0."""
    out = []
    for sub in pe._to_polys(poly):
        if sub.area < 1e-6:
            continue
        m = trimesh.creation.extrude_polygon(sub, height=max(h, 1e-3))
        if z0:
            m.apply_translation([0, 0, z0])
        out.append(m)
    return out


def _build_parts(p):
    fuente = p.get("fuente", "DejaVu Sans")
    size = float(p.get("altura_texto", 50))
    espaciado = float(p.get("espaciado", 0))
    interlinea = float(p.get("interlinea", size * 0.35))
    grosor_letra = float(p.get("grosor_letra", 0))    # engorda(+)/adelgaza(−) el trazo
    prof = float(p.get("profundidad", 16))            # alto total de la caja
    gp = float(p.get("grosor_pared", 2.5))            # grosor de pared exterior
    e_back = float(p.get("grosor_trasera", 1.6))      # grosor del fondo cerrado
    t_tapa = float(p.get("grosor_tapa", 2.0))         # grosor de la tapa (= hondo del encastre)
    labio = float(p.get("labio", 1.3))                # ancho del reborde donde apoya la tapa
    holgura = float(p.get("holgura", 0.25))           # juego de la tapa (mm)
    incluir_tapa = p.get("incluir_tapa", True)
    placa = bool(p.get("placa_trasera"))
    gt = float(p.get("grosor_placa", 2.0))
    color_frente = p.get("color_frente", "#FAFAF0")
    color_caja = p.get("color_caja", "#1E1E1E")

    labio = min(labio, gp * 0.7)                       # el reborde no puede comerse toda la pared
    t_tapa = min(t_tapa, prof - e_back - 0.6)          # deja algo de hueco bajo la tapa
    # altura del escalón donde apoya la tapa/letra:
    if p.get("tope"):
        # TOPE: la letra apoya a media altura y deja un HUECO para el LED debajo
        # (hueco sobre hueco: LED abajo + hueco por delante de la letra).
        hueco_led = float(p.get("hueco_led", 8))
        z_ledge = max(e_back + 1.0, min(e_back + hueco_led, prof - t_tapa - 0.4))
    else:
        z_ledge = prof - t_tapa                        # tapa enrasada arriba (normal)

    l1 = (p.get("linea1", "") or "").strip()
    l2 = (p.get("linea2", "") or "").strip()
    lineas = [t for t in [l1, l2] if t]
    if not lineas:
        raise ValueError("Escribe al menos una linea de texto.")

    # colocar letras en XY (linea 1 arriba) y centrar el conjunto
    polys = []
    n = len(lineas)
    for li, txt in enumerate(lineas):
        cl = pe._line_chars(txt, fuente, size, espaciado)
        yoff = (n - 1 - li) * (size + interlinea)
        for poly in cl:
            for sub in pe._to_polys(poly):
                polys.append(translate(sub, yoff=yoff))
    if not polys:
        raise ValueError("No se pudo generar el texto (¿fuente valida?).")
    allx = np.hstack([np.array(q.exterior.coords)[:, 0] for q in polys])
    ally = np.hstack([np.array(q.exterior.coords)[:, 1] for q in polys])
    cx, cy = (allx.min() + allx.max()) / 2, (ally.min() + ally.max()) / 2
    polys = [translate(q, xoff=-cx, yoff=-cy) for q in polys]
    if p.get("espejo"):                                # texto reflejado (contraluz)
        from shapely.affinity import scale as _sc
        polys = [_sc(q, xfact=-1.0, yfact=1.0, origin=(0, 0)) for q in polys]
    def _bold(ps, b):
        if abs(b) < 1e-3:
            return ps
        out = []
        for q in ps:
            for s in pe._to_polys(q.buffer(b, join_style=1).simplify(size * 0.004)):
                if s.area > 1e-6:
                    out.append(s)
        return out
    objetivo = float(p.get("ancho_hueco_obj", 0) or 0)   # ancho de LED deseado (mm)
    if objetivo > 0:
        # engordar la letra hasta que el canal del LED mida 'objetivo' (bin. search)
        lo, hi = max(-gp + 0.3, -size * 0.3), size * 0.6
        for _ in range(16):
            mid = (lo + hi) / 2.0
            if _ancho_hueco(_bold(polys, mid), gp) < objetivo:
                lo = mid
            else:
                hi = mid
        polys = _bold(polys, (lo + hi) / 2.0)
    elif abs(grosor_letra) > 1e-3:                        # engordar/adelgazar manual
        polys = _bold(polys, grosor_letra)
    # recalcular extremos tras centrar/espejar (para la placa trasera)
    allx = np.hstack([np.array(q.exterior.coords)[:, 0] for q in polys]) + cx
    ally = np.hstack([np.array(q.exterior.coords)[:, 1] for q in polys]) + cy

    ancho_hueco = _ancho_hueco(polys, gp)   # ancho del canal del LED (mm)

    cajas, tapas = [], []
    for poly in polys:
        hueco = poly.buffer(-gp)         # hueco principal (vacío en trazos finos)
        boca = poly.buffer(-labio)       # boca del encastre (más ancha que el hueco)

        # CAJA estanca = bloque macizo − hueco principal − rebaje del encastre
        bloque = trimesh.creation.extrude_polygon(poly, height=prof)
        restar = []
        if not hueco.is_empty:
            for h in pe._to_polys(hueco):          # hueco de e_back hasta arriba
                mm = trimesh.creation.extrude_polygon(h, height=prof - e_back + 0.01)
                mm.apply_translation([0, 0, e_back]); restar.append(mm)
        if not boca.is_empty:
            for b in pe._to_polys(boca):           # rebaje ancho en la boca
                mm = trimesh.creation.extrude_polygon(b, height=prof - z_ledge + 0.01)
                mm.apply_translation([0, 0, z_ledge]); restar.append(mm)
        if restar:
            caja = trimesh.boolean.difference([bloque] + restar, engine="manifold")
        else:
            caja = bloque                          # trazo fino: macizo
        cajas.append(caja)

        # TAPA: entra en la boca con holgura y queda enrasada arriba
        if incluir_tapa and not boca.is_empty:
            tapas += _ext(boca.buffer(-holgura), t_tapa, z_ledge)

    # placa trasera opcional (une letras)
    if placa:
        m = size * 0.28
        rect = Polygon([(allx.min() - cx - m, ally.min() - cy - m),
                        (allx.max() - cx + m, ally.min() - cy - m),
                        (allx.max() - cx + m, ally.max() - cy + m),
                        (allx.min() - cx - m, ally.max() - cy + m)])
        bp = trimesh.creation.extrude_polygon(rect, height=gt)
        bp.apply_translation([0, 0, -gt])
        cajas.append(bp)

    return dict(cajas=cajas, tapas=tapas, cf=color_frente, cc=color_caja,
                ancho_hueco=ancho_hueco)


def build(p):
    """STL: caja + tapa juntas."""
    parts = _build_parts(p)
    m = _concat(parts["cajas"] + parts["tapas"])
    if m is None:
        raise ValueError("Letrero vacio.")
    return m


def build_scene(p):
    """Escena con 2 cuerpos de color para 3MF (caja opaca + tapa translúcida)."""
    parts = _build_parts(p)
    geoms = {}
    cj = _concat(parts["cajas"])
    tp = _concat(parts["tapas"])
    if cj is not None:
        cj.visual.face_colors = pe._hex_rgba(parts["cc"])
        geoms["caja_opaca"] = cj
    if tp is not None:
        tp.visual.face_colors = pe._hex_rgba(parts["cf"])
        geoms["tapa_translucida"] = tp
    return trimesh.Scene(geoms)


def build_preview(p):
    parts = _build_parts(p)
    out = []
    cj = _concat(parts["cajas"])
    tp = _concat(parts["tapas"])
    if cj is not None:
        out.append({"name": "caja", "glow": False, "color": parts["cc"],
                    "v": cj.vertices.astype(np.float32).ravel().tolist(),
                    "f": cj.faces.astype(np.uint32).ravel().tolist()})
    if tp is not None:
        out.append({"name": "tapa", "glow": True, "color": parts["cf"],
                    "v": tp.vertices.astype(np.float32).ravel().tolist(),
                    "f": tp.faces.astype(np.uint32).ravel().tolist()})
    return {"parts": out, "ancho_hueco": round(parts.get("ancho_hueco", 0.0), 1)}


if __name__ == "__main__":
    import sys
    m = build(dict(linea1="BAR", fuente="Arial", altura_texto=60, profundidad=16))
    print("caras:", len(m.faces), "estanco:", m.is_watertight, "ext:", m.extents.round(1))
    m.export(sys.argv[1] if len(sys.argv) > 1 else "letrero.stl")
