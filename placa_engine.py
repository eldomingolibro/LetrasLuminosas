#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor de la "Placa con nombre 3D barrido" (Sweeping name plate).

Genera una BASE (redonda / cuadrada / redondeada / elipse) de la que SALE el
texto en 3D curvandose hacia atras (efecto "sweep"): las letras arrancan
verticales en la base y se inclinan/curvan hacia detras segun suben.

build(params) -> trimesh.Trimesh (solido unido: base + texto)

Parametros (dict):
  linea1, linea2      texto (linea2 opcional)
  fuente              nombre de familia (p.ej. "Arial", "Impact", "DejaVu Sans")
  altura_texto        alto de las letras en mm (tamaño de fuente)
  grosor_texto        grosor/extrusion de las letras en mm (eje Y)
  espaciado           espaciado extra entre letras (mm)
  interlinea          separacion vertical entre las dos lineas (mm)
  curva_grados        cuanto se curva el texto hacia atras (0 = recto) 0..85
  forma_base          "redondeada" | "cuadrada" | "redonda" | "elipse"
  grosor_base         alto de la base en mm
  margen_base         margen de la base alrededor del texto en mm
  fn                  nº de secciones de las curvas de la base
"""
import numpy as np
import trimesh
from functools import reduce

from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union


# ─────────────────────────── texto → poligonos 2D ───────────────────────────
_RES = 600.0   # alto interno de render del glifo (mas = curvas mas suaves)


def _glyphs_polygon(texto, fuente, size, espaciado=0.0):
    """Devuelve un (Multi)Polygon shapely con el contorno del texto (con agujeros
    de letras tipo 'o','a'), apoyado en y=0 y centrado en x=0.

    Los glifos se generan a resolucion _RES (curvas finas) y se reescalan a
    'size', para que no salgan caras planas en las curvas."""
    if not texto:
        return None
    from shapely.affinity import translate, scale
    fp = FontProperties(family=fuente)
    S = _RES                         # tamaño interno alto
    ESP = espaciado * (S / size) if size else espaciado
    if ESP and ESP != 0:
        # construir letra a letra desplazando en x (con espaciado)
        polys = []
        x = 0.0
        for ch in texto:
            if ch == " ":
                x += S * 0.5 + ESP
                continue
            tp = TextPath((0, 0), ch, size=S, prop=fp)
            rings = [r for r in tp.to_polygons() if len(r) >= 3]
            if rings:
                g = reduce(lambda a, b: a.symmetric_difference(b),
                           [Polygon(r).buffer(0) for r in rings])
                minx, miny, maxx, maxy = g.bounds
                g = translate(g, xoff=x - minx)
                polys.append(g)
                x += (maxx - minx) + ESP
            else:
                x += S * 0.3 + ESP
        geom = unary_union(polys) if polys else None
    else:
        tp = TextPath((0, 0), texto, size=S, prop=fp)
        rings = [r for r in tp.to_polygons() if len(r) >= 3]
        if not rings:
            return None
        geom = reduce(lambda a, b: a.symmetric_difference(b),
                      [Polygon(r).buffer(0) for r in rings])
    if geom is None or geom.is_empty:
        return None
    # reescalar de _RES -> size y centrar en x, apoyar en y=0
    geom = scale(geom, xfact=size / S, yfact=size / S, origin=(0, 0))
    # simplificar un pelin (quita puntos redundantes sin facetar las curvas)
    geom = geom.simplify(size * 0.004, preserve_topology=True)
    minx, miny, maxx, maxy = geom.bounds
    geom = translate(geom, xoff=-(minx + maxx) / 2.0, yoff=-miny)
    return geom


def _to_polys(geom):
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if g.area > 1e-6]
    if isinstance(geom, Polygon):
        return [geom]
    # GeometryCollection
    out = []
    for g in getattr(geom, "geoms", []):
        if isinstance(g, Polygon) and g.area > 1e-6:
            out.append(g)
    return out


# ─────────────────────────── barrido (sweep en arco) ────────────────────────
def _fan_solid(poly, grados, Ri=0.6, N=44):
    """ABANICO: gira la letra alrededor de su base en N capas. La cara TRASERA
    queda tumbada sobre la base (phi=90) y la cara FRONTAL se abre hasta vertical
    cuando grados=90. Al BAJAR 'grados' la cara frontal se cierra hacia delante
    (se tumba), manteniendo anclado el abanico. Devuelve un Trimesh solido.
      poly: Polygon en (x=horizontal, h=altura>=0).  Ri: radio interior minimo."""
    from collections import defaultdict
    ang = np.radians(float(grados))
    if ang < 1e-4:                        # recto tumbado: casi plano
        ang = np.radians(1.0)

    v2, faces = trimesh.creation.triangulate_polygon(poly, engine="earcut")
    M = len(v2)
    x = v2[:, 0]; h = v2[:, 1]; r = Ri + h
    # abanico entre la cara frontal (90-grados) y la trasera tumbada (90°)
    phi0 = np.radians(90.0) - ang
    phis = np.linspace(phi0, np.radians(90.0), N + 1)
    V = np.vstack([np.column_stack([x, r * np.sin(ph), r * np.cos(ph)])
                   for ph in phis])

    # aristas de borde DIRIGIDAS (tal y como aparecen en su triangulo CCW): asi
    # los muros salen con la orientacion correcta sin necesitar fix_normals.
    ef = defaultdict(list)
    for t in faces:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            ef[(min(a, b), max(a, b))].append((a, b))
    borde = np.array([v[0] for v in ef.values() if len(v) == 1], dtype=np.int64)

    # muros vectorizados: para cada arista dirigida (i->j) y cada capa k
    i = borde[:, 0]; j = borde[:, 1]
    k = np.arange(N)[:, None]
    A = k * M + i[None, :]; B = k * M + j[None, :]
    C = (k + 1) * M + j[None, :]; D = (k + 1) * M + i[None, :]
    t1 = np.stack([A, D, C], axis=-1).reshape(-1, 3)
    t2 = np.stack([A, C, B], axis=-1).reshape(-1, 3)
    F = np.vstack([faces,                # cara frontal
                   faces[:, ::-1] + N * M,  # cara trasera
                   t1, t2])
    # orientacion correcta por construccion -> volumen valido sin fix_normals
    return trimesh.Trimesh(vertices=V, faces=F, process=False)


def _extruir(geom, grosor):
    """Extruye un (Multi)Polygon en Z por 'grosor'."""
    mallas = [trimesh.creation.extrude_polygon(poly, height=grosor)
              for poly in _to_polys(geom)]
    if not mallas:
        return None
    return trimesh.util.concatenate(mallas) if len(mallas) > 1 else mallas[0]


# ─────────────────────────── base ───────────────────────────────────────────
def _rounded_rect(w, d, r, fn=48):
    """Rectangulo redondeado (w x d) centrado en el origen, como poligono."""
    r = max(0.0, min(r, min(w, d) / 2.0 - 1e-3))
    if r <= 1e-3:
        hw, hd = w / 2.0, d / 2.0
        return Polygon([(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)])
    hw, hd = w / 2.0 - r, d / 2.0 - r
    pts = []
    centros = [(hw, hd, 0), (-hw, hd, 90), (-hw, -hd, 180), (hw, -hd, 270)]
    per = max(4, fn // 4)
    for cx, cy, a0 in centros:
        for k in range(per + 1):
            a = np.radians(a0 + 90.0 * k / per)
            pts.append((cx + r * np.cos(a), cy + r * np.sin(a)))
    return Polygon(pts)


def _base_polygon(forma, w, d, fn):
    if forma == "cuadrada":
        return _rounded_rect(w, d, 0, fn)
    if forma == "redonda":
        R = max(w, d) / 2.0
        a = np.linspace(0, 2 * np.pi, max(16, fn), endpoint=False)
        return Polygon(np.column_stack([R * np.cos(a), R * np.sin(a)]))
    if forma == "elipse":
        a = np.linspace(0, 2 * np.pi, max(16, fn), endpoint=False)
        return Polygon(np.column_stack([(w / 2.0) * np.cos(a),
                                        (d / 2.0) * np.sin(a)]))
    # redondeada (por defecto)
    return _rounded_rect(w, d, min(w, d) * 0.18, fn)


# ─────────────────────────── texto letra a letra ────────────────────────────
def _char_poly(ch, fuente, size):
    """Poligono de UN caracter, alto a alta resolucion y escalado a 'size',
    alineado a la izquierda (minx=0) y apoyado en y=0. Devuelve (poly, ancho) o
    None (espacio/sin contorno)."""
    from shapely.affinity import translate, scale
    fp = FontProperties(family=fuente)
    tp = TextPath((0, 0), ch, size=_RES, prop=fp)
    rings = [r for r in tp.to_polygons() if len(r) >= 3]
    if not rings:
        return None
    g = reduce(lambda a, b: a.symmetric_difference(b),
               [Polygon(r).buffer(0) for r in rings])
    if g is None or g.is_empty:
        return None
    g = scale(g, xfact=size / _RES, yfact=size / _RES, origin=(0, 0))
    g = g.simplify(size * 0.004, preserve_topology=True)
    minx, miny, maxx, maxy = g.bounds
    g = translate(g, xoff=-minx, yoff=-miny)
    return g, (maxx - minx)


def _line_chars(txt, fuente, size, espaciado):
    """Lista de poligonos (uno por caracter visible, en orden de lectura) de una
    linea, colocados con su avance y centrados como grupo en x=0, base en y=0."""
    from shapely.affinity import translate
    polys = []
    x = 0.0
    gap_nat = size * 0.12                 # separacion natural entre letras
    for ch in txt:
        if ch == " ":
            x += size * 0.42 + espaciado
            continue
        cp = _char_poly(ch, fuente, size)
        if cp is None:
            x += size * 0.3 + espaciado
            continue
        poly, w = cp
        polys.append(translate(poly, xoff=x))
        x += w + gap_nat + espaciado
    if not polys:
        return []
    minx = min(p.bounds[0] for p in polys)
    maxx = max(p.bounds[2] for p in polys)
    shift = -(minx + maxx) / 2.0
    return [translate(p, xoff=shift) for p in polys]


def _hex_rgba(h, a=255):
    h = (h or "").lstrip("#")
    if len(h) != 6:
        return [230, 150, 60, a]
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a]


# ─────────────────────────── construccion de piezas ─────────────────────────
def _build_parts(p):
    """Construye las piezas: base + una por cada letra (con su color). Devuelve
    dict(base, base_color, letras=[(mesh, color_hex), ...] en orden de lectura).
    Soporta desplazamiento del texto (pos_x, pos_y)."""
    fuente = p.get("fuente", "DejaVu Sans")
    size = float(p.get("altura_texto", 18))
    espaciado = float(p.get("espaciado", 0))
    interlinea = float(p.get("interlinea", size * 0.4))
    grados = float(p.get("curva_grados", 90))
    forma = p.get("forma_base", "redondeada")
    grosor_base = float(p.get("grosor_base", 4))     # alto Z de la base
    margen = float(p.get("margen_base", 10))
    base_ancho = float(p.get("base_ancho", 0))       # X manual (0 = auto)
    base_fondo = float(p.get("base_fondo", 0))       # Y manual (0 = auto)
    fn = int(p.get("fn", 64))
    pos_x = float(p.get("pos_x", 0))
    pos_y = float(p.get("pos_y", 0))
    grosor_letra = float(p.get("grosor_letra", 0))   # engorda(+)/adelgaza(-) mm
    color_base = p.get("color_base", "#c8a06e")
    colores = p.get("colores") or []
    color_txt = p.get("color_texto", "#e69630")

    l1 = (p.get("linea1", "") or "").strip()
    l2 = (p.get("linea2", "") or "").strip()
    lineas = [t for t in [l1, l2] if t]        # orden de lectura
    if not lineas:
        raise ValueError("Escribe al menos una linea de texto.")

    # caracteres por linea (orden de lectura) y color global por letra
    chars_por_linea = [_line_chars(t, fuente, size, espaciado) for t in lineas]
    base_idx = []
    acc = 0
    for cl in chars_por_linea:
        base_idx.append(acc); acc += len(cl)

    def color_de(ci):
        if ci < len(colores) and colores[ci]:
            return colores[ci]
        return color_txt

    # profundidad: la ultima linea (l2) delante, la primera (l1) detras
    orden_prof = list(reversed(range(len(lineas))))
    gap = size * 0.5
    letras = []                                # (mesh, color_hex, color_idx)
    y_cursor = 0.0
    for li in orden_prof:
        chars = chars_por_linea[li]
        if not chars:
            continue
        metas = []
        prof = 0.0
        for j, poly in enumerate(chars):
            # engordar/adelgazar la letra (buffer del contorno)
            pg = poly
            if abs(grosor_letra) > 1e-3:
                pg = poly.buffer(grosor_letra, join_style=1).simplify(size * 0.004)
            subs = _to_polys(pg)
            if not subs:
                continue
            fans = [_fan_solid(s, grados) for s in subs]
            m = trimesh.util.concatenate(fans) if len(fans) > 1 else fans[0]
            prof = max(prof, float(m.vertices[:, 1].max() - m.vertices[:, 1].min()))
            metas.append((m, base_idx[li] + j))
        for m, ci in metas:
            m.apply_translation([0, y_cursor, 0])
            letras.append((m, color_de(ci), ci))
        y_cursor += prof + gap
    if not letras:
        raise ValueError("No se pudo generar el texto (¿fuente valida?).")

    # BASE segun el footprint natural del texto (sin el desplazamiento)
    allv = np.vstack([m.vertices for m, _, _ in letras])
    minx, maxx = allv[:, 0].min(), allv[:, 0].max()
    miny, maxy = allv[:, 1].min(), allv[:, 1].max()
    w = base_ancho if base_ancho > 0 else (maxx - minx) + 2 * margen
    d = base_fondo if base_fondo > 0 else (maxy - miny) + 2 * margen
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    base_poly = _base_polygon(forma, w, d, fn)
    base = trimesh.creation.extrude_polygon(base_poly, height=grosor_base)
    base.apply_translation([cx, cy, -grosor_base + 0.2])

    # desplazar el TEXTO sobre la base (mover como objeto en X/Y)
    if pos_x or pos_y:
        for m, _, _ in letras:
            m.apply_translation([pos_x, pos_y, 0])

    # apoyar en z=0: la cara inferior de la base queda en z=0 (nada bajo el plano)
    minz = min([base.vertices[:, 2].min()] + [m.vertices[:, 2].min() for m, _, _ in letras])
    if abs(minz) > 1e-9:
        base.apply_translation([0, 0, -minz])
        for m, _, _ in letras:
            m.apply_translation([0, 0, -minz])

    return dict(base=base, base_color=color_base, letras=letras)  # (m, color, ci)


# ─────────────────────────── salidas ────────────────────────────────────────
def build(p):
    """STL: union de base + letras en un solido unico."""
    parts = _build_parts(p)
    piezas = [parts["base"]] + [m for m, _, _ in parts["letras"]]
    solido = trimesh.boolean.union(piezas, engine="manifold")
    return solido


def build_scene(p):
    """Escena con cuerpos de color (base + cada letra) para exportar 3MF/GLB."""
    parts = _build_parts(p)
    geoms = {}
    b = parts["base"].copy()
    b.visual.face_colors = _hex_rgba(parts["base_color"])
    geoms["base"] = b
    for i, (m, col, ci) in enumerate(parts["letras"]):
        mm = m.copy()
        mm.visual.face_colors = _hex_rgba(col)
        geoms[f"letra_{ci:02d}"] = mm
    return trimesh.Scene(geoms)


def build_preview(p):
    """Datos ligeros para el visor: cada pieza con sus vertices, caras y color.
    'base' y las letras por separado (para colorear y mover el texto)."""
    parts = _build_parts(p)
    out = []
    bv = parts["base"]
    out.append({"name": "base", "text": False, "color": parts["base_color"],
                "v": bv.vertices.astype(np.float32).ravel().tolist(),
                "f": bv.faces.astype(np.uint32).ravel().tolist()})
    for (m, col, ci) in parts["letras"]:
        out.append({"name": f"letra_{ci}", "ci": ci, "text": True, "color": col,
                    "v": m.vertices.astype(np.float32).ravel().tolist(),
                    "f": m.faces.astype(np.uint32).ravel().tolist()})
    return out


if __name__ == "__main__":
    import sys
    params = dict(linea1="Laura", linea2="Perales", fuente="Arial",
                  altura_texto=16, grosor_texto=6, curva_grados=55,
                  forma_base="redondeada", grosor_base=4, margen_base=10)
    m = build(params)
    print("watertight:", m.is_watertight, "| caras:", len(m.faces),
          "| extents:", m.extents.round(1))
    out = sys.argv[1] if len(sys.argv) > 1 else "test_placa.stl"
    m.export(out)
    print("->", out)
