#!/usr/bin/env python3
"""Join Census 2021 population into admin GPKG + add density choropleth layers.

- population (Tot_P_P, Census 2021 usual residents) + pop_density (p/km2)
  written into lga (LGA_CODE25, via 2021->2025 correspondence chain) and
  sal (SAL_CODE21, direct) of both admin GPKPs.
- Two graduated-color layers added to the project ABOVE the admin SAL layer,
  UNCHECKED by default (admin colors and density colors clash when both on).

Usage: python3 add_population.py <project.qgs> [more.qgs ...]
"""
import csv
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import (
    QgsApplication, QgsProject, QgsVectorLayer, QgsField, QgsFillSymbol,
    QgsGraduatedSymbolRenderer, QgsRendererRange, QgsLayerTreeLayer)
from PyQt5.QtCore import QVariant
from PyQt5.QtGui import QColor

DATA = os.path.expanduser("~/qgis-data/abs-2021-census")
GPKGS = [
    os.path.expanduser("~/qgis-data/au-admin/admin_boundaries_3857.gpkg"),
    os.path.expanduser("~/qgis-data/au-admin/admin_boundaries.gpkg"),
]
CORR = ["CG_LGA_2021_LGA_2022.csv", "CG_2022_LGA_2023_LGA.csv",
        "CG_LGA_2023_LGA_2024.csv", "CG_LGA_2024_LGA_2025.csv"]
RAMP = ["#ffffcc", "#ffeda0", "#feb24c", "#f03b20", "#bd0026"]


def log(m):
    print(f"[pop] {m}", flush=True)


def load_population():
    pop = {}
    with open(f"{DATA}/2021Census_G01_AUST_LGA.csv") as f:
        for row in csv.DictReader(f):
            v = row.get("Tot_P_P", "")
            pop[row["LGA_CODE_2021"][3:]] = int(v) if v else None
    sal = {}
    with open(f"{DATA}/2021Census_G01_AUST_SAL.csv") as f:
        for row in csv.DictReader(f):
            v = row.get("Tot_P_P", "")
            sal[row["SAL_CODE_2021"][3:]] = int(v) if v else None
    return pop, sal


def propagate_lga(pop):
    """2021 populations -> 2025 boundaries via 4-step correspondence chain."""
    for fname in CORR:
        rows = list(csv.DictReader(open(f"{DATA}/{fname}")))
        cols = [c for c in rows[0] if c.upper().startswith("LGA_CODE")]
        ratio_c = next(c for c in rows[0] if "RATIO" in c.upper())
        cf, ct = cols[0], cols[1]
        froms = {r[cf] for r in rows}
        nxt = {}
        for r in rows:
            p = pop.get(r[cf]) or 0
            nxt[r[ct]] = nxt.get(r[ct], 0) + p * float(r[ratio_c] or 0)
        for code, p in pop.items():
            if code not in froms:
                nxt[code] = nxt.get(code, 0) + (p or 0)
        pop = {k: (round(v) if v else None) for k, v in nxt.items()}
    return pop


def write_fields(gpkg, layer_name, code_field, pop_map, area_field):
    lyr = QgsVectorLayer(f"{gpkg}|layername={layer_name}", layer_name, "ogr")
    if not lyr.isValid():
        sys.exit(f"invalid {gpkg} {layer_name}")
    have = {f.name() for f in lyr.fields()}
    add = [QgsField(n, t) for n, t in
           (("population", QVariant.Int), ("pop_density", QVariant.Double))
           if n not in have]
    if add:
        lyr.dataProvider().addAttributes(add)
        lyr.updateFields()
    lyr.reload()
    i_pop, i_den = (lyr.fields().indexOf(n) for n in ("population", "pop_density"))
    changes, densities = {}, {}
    for f in lyr.getFeatures():
        code = f[code_field]
        p = pop_map.get(code)
        area = f[area_field]
        den = (p / area) if (p is not None and area) else None
        changes[f.id()] = {i_pop: p, i_den: round(den, 2) if den is not None else None}
        if den is not None:
            densities[code] = den
    lyr.dataProvider().changeAttributeValues(changes)
    lyr.reload()
    return len(changes), sum(1 for f in lyr.getFeatures() if f["population"] is not None), densities


def nice(v):
    if v <= 0:
        return 0
    mag = 10 ** (len(str(int(v))) - 1)
    return max(1, round(v / mag) * mag)


def quantile_breaks(vals, ncls):
    sv = sorted(vals)
    qs = [sv[min(len(sv) - 1, int(len(sv) * (i + 1) / ncls - 1e-9))] for i in range(ncls)]
    uniq = sorted(set(nice(q) for q in qs))
    out = []
    for q in uniq:
        if not out or q > out[-1]:
            out.append(q)
    return out


def ramp_color(t):
    t = min(1.0, max(0.0, t)) * (len(RAMP) - 1)
    i = min(int(t), len(RAMP) - 2)
    f = t - i
    c1, c2 = QColor(RAMP[i]), QColor(RAMP[i + 1])
    mix = QColor(
        int(c1.red() + (c2.red() - c1.red()) * f),
        int(c1.green() + (c2.green() - c1.green()) * f),
        int(c1.blue() + (c2.blue() - c1.blue()) * f))
    return mix.name()


def make_renderer(densities, breaks):
    """Graduated renderer with explicit pretty breaks (persons/km2)."""
    lo = 0.0
    ranges, syms = [], []          # keep refs alive: C++ holds raw pointers
    for k, hi in enumerate(breaks):
        sym = QgsFillSymbol.createSimple({
            "color": ramp_color((k + 1) / len(breaks)),
            "outline_color": "#666666", "outline_width": "0.1"})
        sym.setOpacity(0.6)
        syms.append(sym)
        ranges.append(QgsRendererRange(lo, hi, sym, f"≤ {hi:,} 人/km²"))
        lo = hi
    sym = QgsFillSymbol.createSimple({
        "color": ramp_color(1.0), "outline_color": "#666666",
        "outline_width": "0.1"})
    sym.setOpacity(0.6)
    syms.append(sym)
    ranges.append(QgsRendererRange(lo, 1e12, sym, f"> {breaks[-1]:,} 人/km²"))
    r = QgsGraduatedSymbolRenderer("pop_density", ranges)
    return r, breaks


def add_layers(proj, lga_breaks, sal_breaks):
    gpkg = GPKGS[0]
    pop_lga = QgsVectorLayer(f"{gpkg}|layername=lga", "人口密度·LGA(区/市)", "ogr")
    pop_sal = QgsVectorLayer(f"{gpkg}|layername=sal", "人口密度·SAL(郊区)", "ogr")
    pop_lga.setRenderer(make_renderer(
        {f["LGA_CODE25"]: f["pop_density"] for f in pop_lga.getFeatures()
         if f["pop_density"] is not None}, lga_breaks)[0])
    pop_sal.setRenderer(make_renderer(
        {f["SAL_CODE21"]: f["pop_density"] for f in pop_sal.getFeatures()
         if f["pop_density"] is not None}, sal_breaks)[0])
    for lyr in (pop_lga, pop_sal):
        proj.addMapLayer(lyr, False)

    root = proj.layerTreeRoot()
    log("step1: tree root ok")
    for lid, lyr in list(proj.mapLayers().items()):
        if lyr.name().startswith("人口密度"):
            if lid not in (pop_lga.id(), pop_sal.id()):
                proj.removeMapLayer(lid)
    log("step2: idempotent cleanup ok")
    node = None
    for rl in root.findLayers():
        if rl.layer() and rl.layer().name().startswith("行政区划·SAL"):
            node = rl
            break
    i = node.parent().children().index(node)
    log(f"step3: found admin SAL node at idx {i}")
    n_lga = QgsLayerTreeLayer(pop_lga)
    n_sal = QgsLayerTreeLayer(pop_sal)
    parent = node.parent()
    parent.insertChildNode(i, n_lga)
    parent.insertChildNode(i + 1, n_sal)
    n_lga.setItemVisibilityChecked(False)
    n_sal.setItemVisibilityChecked(False)
    log("step4: nodes inserted + unchecked")


def ensure_fields():
    """Idempotent: write population/pop_density into both GPKGs."""
    pop_lga21, pop_sal = load_population()
    log(f"census raw: LGA {len(pop_lga21)} SAL {len(pop_sal)}")
    pop_lga25 = propagate_lga(pop_lga21)
    log(f"LGA 2021->2025 propagated: {len(pop_lga25)} codes")
    dens = {}
    for gpkg in GPKGS:
        n, matched, d = write_fields(gpkg, "lga", "LGA_CODE25", pop_lga25, "AREASQKM")
        log(f"{os.path.basename(gpkg)} lga: {matched}/{n} matched")
        n, matched, d2 = write_fields(gpkg, "sal", "SAL_CODE21", pop_sal, "AREASQKM21")
        log(f"{os.path.basename(gpkg)} sal: {matched}/{n} matched")
        dens = d
    return dens


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("--") else "--all"
    rest = [a for a in sys.argv[1:] if not a.startswith("--")]
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    QgsApplication.initQgis()
    if mode in ("--fields-only", "--all"):
        ensure_fields()
    if mode in ("--layers-only", "--all"):
        for p in rest:
            proj = QgsProject()
            proj.read(p)
            add_layers(proj, [5, 25, 100, 300, 1000, 3000],
                       [10, 50, 200, 800, 2500, 8000, 20000])
            proj.write(p)
            print(f"saved {p}")
    QgsApplication.exitQgis()
    sys.stdout.flush()
    os._exit(0)   # 跳过解释器退出阶段,规避 PyQGIS 已知的退出段崩(写盘已完成)


if __name__ == "__main__":
    main()
