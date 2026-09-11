#!/usr/bin/env python3
"""Add admin boundary color-block layers to a QGIS project.

Adds two polygon layers from au-admin/admin_boundaries.gpkg, styled as
semi-transparent color blocks with text labels, inserted right above the
raster tile basemap:

  行政区划·LGA (city->district blocks)   always visible, name labels <= 1:250k
  行政区划·SAL (suburb/locality blocks)  visible <= 1:150k, name labels <= 1:60k
        - same LGA => same hue (grouped by administrative centre town)
        - centre town (is_centre=1): bold-ish bigger label + thicker outline

Usage: python3 add_admin_layers.py <project.qgs> [more.qgs ...]
"""
import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtGui import QColor, QFont
from qgis.core import (
    QgsApplication, QgsProject, QgsVectorLayer, QgsFillSymbol,
    QgsSingleSymbolRenderer, QgsPalLayerSettings, QgsTextFormat,
    QgsTextBufferSettings, QgsVectorLayerSimpleLabeling, QgsProperty,
    QgsUnitTypes, QgsLayerTreeLayer, QgsSymbolLayer)

GPKG = os.environ.get(
    "ADMIN_GPKG",
    os.path.expanduser("~/qgis-data/au-admin/admin_boundaries_3857.gpkg"))


def pick_field(layer, pattern):
    rx = re.compile(pattern, re.I)
    for f in layer.fields():
        if rx.match(f.name()):
            return f.name()
    return None


def dd_fill_color(sym, field):
    """Data-defined fill color from a field."""
    sl = sym.symbolLayer(0)
    props = sl.dataDefinedProperties()
    props.setProperty(QgsSymbolLayer.PropertyFillColor,
                      QgsProperty.fromField(field))
    sl.setDataDefinedProperties(props)


def dd_stroke_width(sym, expression):
    sl = sym.symbolLayer(0)
    props = sl.dataDefinedProperties()
    props.setProperty(QgsSymbolLayer.PropertyStrokeWidth,
                      QgsProperty.fromExpression(expression))
    sl.setDataDefinedProperties(props)


def make_labels(field, size, max_scale, bold_expr=None, size_expr=None):
    """PAL labels with white buffer + scale visibility."""
    s = QgsPalLayerSettings()
    s.fieldName = field
    s.placement = QgsPalLayerSettings.Horizontal
    s.isExpression = False
    fmt = QgsTextFormat()
    fmt.setFont(QFont("DejaVu Sans"))
    fmt.setSize(size)
    fmt.setSizeUnit(QgsUnitTypes.RenderPoints)
    fmt.setColor(QColor("#111111"))
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(1.8)
    buf.setSizeUnit(QgsUnitTypes.RenderPoints)
    buf.setColor(QColor("#ffffff"))
    fmt.setBuffer(buf)
    s.setFormat(fmt)
    s.scaleVisibility = True
    # QGIS semantics: visible iff maximumScale <= scale <= minimumScale
    # (maximumScale = most-zoomed-IN bound). So "labels appear when zoomed
    #  in past 1:max_scale" means minimumScale = max_scale, maximumScale = 0.
    s.minimumScale = max_scale
    s.maximumScale = 0
    ddp = s.dataDefinedProperties()
    if size_expr:
        ddp.setProperty(QgsPalLayerSettings.Size,
                        QgsProperty.fromExpression(size_expr))
    if bold_expr:                        # centre town -> Bold
        try:
            ddp.setProperty(QgsPalLayerSettings.NamedStyle,
                            QgsProperty.fromExpression(bold_expr))
        except Exception:
            pass
    s.setDataDefinedProperties(ddp)
    return QgsVectorLayerSimpleLabeling(s)


def style_lga(layer, name_field):
    sym = QgsFillSymbol.createSimple({
        "color": "#ffffff", "outline_color": "#222222",
        "outline_width": "0.25"})
    dd_fill_color(sym, "fill_color")
    sym.setOpacity(0.30)
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.setLabeling(make_labels(name_field, 10.5, 250000))
    layer.setLabelsEnabled(True)


def style_sal(layer, name_field):
    sym = QgsFillSymbol.createSimple({
        "color": "#ffffff", "outline_color": "#222222",
        "outline_width": "0.15"})
    dd_fill_color(sym, "fill_color")
    dd_stroke_width(sym, 'if("is_centre"=1, 0.66, 0.15)')
    sym.setOpacity(0.38)
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.setLabeling(make_labels(
        name_field, 8.5, 60000,
        bold_expr='if("is_centre"=1, \'Bold\', \'Regular\')',
        size_expr='if("is_centre"=1, 10.5, 8.5)'))
    layer.setLabelsEnabled(True)
    layer.setScaleBasedVisibility(True)
    layer.setMinimumScale(150000)       # zoomed-out bound: visible <= 1:150k
    layer.setMaximumScale(0)


def add_to_project(path):
    proj = QgsProject()
    proj.read(path)
    print(f"loaded {path} ({len(proj.mapLayers())} layers)")

    # idempotent: drop admin layers from a previous run
    for lid, lyr in list(proj.mapLayers().items()):
        name = lyr.name()
        if name.startswith("行政区划"):
            proj.removeMapLayer(lid)
            print(f"removed previous {name}")

    lga = QgsVectorLayer(f"{GPKG}|layername=lga", "行政区划·LGA(区/市)", "ogr")
    sal = QgsVectorLayer(f"{GPKG}|layername=sal", "行政区划·SAL(城镇/郊区)", "ogr")
    for lyr in (lga, sal):
        if not lyr.isValid():
            sys.exit(f"layer invalid: {lyr.name()}")
    lga_name = pick_field(lga, r"LGA_NAME")
    sal_name = pick_field(sal, r"SAL_NAME")
    style_lga(lga, lga_name)
    style_sal(sal, sal_name)
    print(f"label fields: lga={lga_name} sal={sal_name}")

    proj.addMapLayer(lga, False)
    proj.addMapLayer(sal, False)

    # insert ABOVE the raster basemap (below everything else)
    root = proj.layerTreeRoot()
    node = None
    for rl in root.findLayers():
        if rl.layer() and rl.layer().type() == 1 \
                and not rl.layer().name().startswith("地形"):
            node = rl          # the XYZ basemap, not terrain rasters
            break
    if node is not None:
        parent = node.parent()
        i = parent.children().index(node)
        parent.insertChildNode(i, QgsLayerTreeLayer(sal))     # sal above lga
        parent.insertChildNode(i + 1, QgsLayerTreeLayer(lga))
        print(f"inserted above raster '{node.name()}' in "
              f"'{parent.name() or 'root'}' at idx {i}")
    else:
        root.insertLayer(0, sal)
        root.insertLayer(0, lga)
        print("no raster found; inserted at panel top")

    enable_all_labels(proj)
    proj.write(path)
    print(f"saved {path}")


def enable_all_labels(proj):
    """Admin blocks want every name shown, even slightly colliding."""
    from qgis.core import QgsLabelingEngineSettings
    eng = proj.labelingEngineSettings()
    eng.setFlag(QgsLabelingEngineSettings.UseAllLabels, True)
    proj.setLabelingEngineSettings(eng)


def main():
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    QgsApplication.initQgis()
    for p in sys.argv[1:]:
        add_to_project(p)
    QgsApplication.exitQgis()
    sys.stdout.flush()
    os._exit(0)   # 跳过解释器退出阶段,规避 PyQGIS 已知的退出段崩(写盘已完成)


if __name__ == "__main__":
    main()
