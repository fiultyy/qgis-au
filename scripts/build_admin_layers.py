#!/usr/bin/env python3
"""SAL -> LGA spatial join + centre-town flag + color precompute.

For every SAL (suburb/locality) finds the LGA containing its centroid
(fallback: nearest LGA), then writes columns into the GPKG via sqlite:
  sal: lga_code, lga_name, is_centre, fill_color
  lga: fill_color

Colors: hue = hash(lga_code) so all suburbs of one LGA share the same hue
("suburbs grouped by their administrative centre town"); SAL lightness is
varied within the LGA so neighbouring blocks stay distinguishable.

Usage: python3 build_admin_layers.py
"""
import colorsys
import hashlib
import os
import re
import sqlite3
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import QVariant
from qgis.core import (QgsApplication, QgsVectorLayer, QgsSpatialIndex,
                       QgsRectangle, QgsFeature, QgsField)

GPKG = os.path.expanduser("~/qgis-data/au-admin/admin_boundaries.gpkg")


def log(m):
    print(f"[join] {m}", flush=True)


def pick_field(layer, pattern):
    rx = re.compile(pattern, re.I)
    for f in layer.fields():
        if rx.match(f.name()):
            return f.name()
    return None


def hue_of(key: str) -> int:
    return int(hashlib.md5(key.encode()).hexdigest()[:6], 16) % 360


def hex_color(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s, v)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def norm_name(n: str) -> str:
    return re.sub(r"\s*\([A-Z]+\)$", "", n or "").strip().casefold()


def main():
    app = QgsApplication([], False)
    QgsApplication.initQgis()

    sal = QgsVectorLayer(f"{GPKG}|layername=sal", "sal", "ogr")
    lga = QgsVectorLayer(f"{GPKG}|layername=lga", "lga", "ogr")
    if not (sal.isValid() and lga.isValid()):
        sys.exit(f"layers invalid: sal={sal.isValid()} lga={lga.isValid()}")

    lga_code_f = pick_field(lga, r"LGA_CODE")
    lga_name_f = pick_field(lga, r"LGA_NAME")
    sal_code_f = pick_field(sal, r"SAL_CODE")
    sal_name_f = pick_field(sal, r"SAL_NAME")
    log(f"fields: lga {lga_code_f}/{lga_name_f} | sal {sal_code_f}/{sal_name_f}")
    if not all([lga_code_f, lga_name_f, sal_code_f, sal_name_f]):
        sys.exit("field introspection failed")

    # index LGA and keep geometries
    lga_feats = {}
    idx = QgsSpatialIndex()
    for f in lga.getFeatures():
        lga_feats[f.id()] = (f[lga_code_f], f[lga_name_f], f.geometry())
        idx.addFeature(f)

    updates = {}          # sal_code -> dict
    n_centre = n_unmatched = 0
    for f in sal.getFeatures():
        sc, sn = f[sal_code_f], f[sal_name_f]
        if not f.hasGeometry():
            updates[sc] = (None, None, 0, "#9e9e9e")
            n_unmatched += 1
            continue
        c = f.geometry().centroid().asPoint()
        match = None
        for cand in idx.intersects(QgsRectangle(c.x(), c.y(), c.x(), c.y())):
            code, name, geom = lga_feats[cand]
            if geom.contains(c):
                match = (code, name)
                break
        if match is None:                       # fallback: nearest LGA
            nid = idx.nearestNeighbor(c, 1)
            if nid:
                code, name, _ = lga_feats[nid[0]]
                match = (code, name)
        if match is None:
            updates[sc] = (None, None, 0, "#9e9e9e")
            n_unmatched += 1
            continue
        code, name = match
        centre = 1 if norm_name(sn) == norm_name(name) else 0
        n_centre += centre
        h = hue_of(str(code))
        light = 0.52 + (int(hashlib.md5(str(sc).encode()).hexdigest()[:4], 16) % 3) * 0.09
        updates[sc] = (code, name, centre, hex_color(h, 0.55, 0.76 if light > 0.6 else 0.68))

    # write results back via PyQGIS provider (handles GPKG triggers safely)
    def ensure_cols(layer, cols):
        have = {f.name() for f in layer.fields()}
        add = [QgsField(n, t) for n, t in cols if n not in have]
        if add:
            layer.dataProvider().addAttributes(add)
            layer.updateFields()

    ensure_cols(sal, [("lga_code", QVariant.String), ("lga_name", QVariant.String),
                      ("is_centre", QVariant.Int), ("fill_color", QVariant.String)])
    ensure_cols(lga, [("fill_color", QVariant.String)])
    sal.reload()
    lga.reload()
    sal_flds = {n: sal.fields().indexOf(n) for n in
                ("lga_code", "lga_name", "is_centre", "fill_color")}
    lga_flds = {n: lga.fields().indexOf(n) for n in ("fill_color",)}

    changes = {}
    for f in sal.getFeatures():
        v = updates.get(f[sal_code_f])
        if v:
            changes[f.id()] = {sal_flds["lga_code"]: v[0], sal_flds["lga_name"]: v[1],
                               sal_flds["is_centre"]: v[2], sal_flds["fill_color"]: v[3]}
    sal.dataProvider().changeAttributeValues(changes)

    lga_changes = {fid: {lga_flds["fill_color"]: hex_color(hue_of(str(code)), 0.55, 0.72)}
                   for fid, (code, name, geom) in lga_feats.items()}
    lga.dataProvider().changeAttributeValues(lga_changes)
    log(f"SAL joined: {len(changes)} | centre towns: {n_centre} | "
        f"unmatched: {n_unmatched}")
    QgsApplication.exitQgis()


if __name__ == "__main__":
    main()
