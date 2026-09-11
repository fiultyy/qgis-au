#!/usr/bin/env python3
"""生成聚合工程 au-property-master.qgs — 全部可用数据层"""
from qgis.core import (
    QgsApplication, QgsProject, QgsVectorLayer, QgsRasterLayer,
    QgsCoordinateReferenceSystem, QgsFillSymbol, QgsMarkerSymbol,
    QgsCategorizedSymbolRenderer, QgsRendererCategory,
    QgsSingleSymbolRenderer, QgsRectangle,
)

QgsApplication.setPrefixPath("/usr", True)
app = QgsApplication([], False)
QgsApplication.initQgis()

proj = QgsProject.instance()
proj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

ok = []

# ═══ 1. 底图: 本地瓦片 z0-17 ═══
tiles = QgsRasterLayer(
    "type=xyz&url=http://127.0.0.1:8088/{z}/{x}/{y}.png&zmin=0&zmax=17",
    "本地瓦片底图 z0-17", "wms")
if tiles.isValid():
    proj.addMapLayer(tiles); ok.append("底图")

# ═══ 2. NSW 地块边界 (5.28M) ═══
cad = QgsVectorLayer(
    "/home/yy/qgis-data/nsw-cadastre-merged.gpkg|layername=nsw_cadastre",
    "NSW 地块边界 (5.28M)", "ogr")
if cad.isValid():
    sym = QgsFillSymbol.createSimple({
        "color": "0,0,0,0",           # 透明填充
        "outline_color": "255,140,0,180",  # 橙色边线
        "outline_width": "0.4"
    })
    cad.setRenderer(QgsSingleSymbolRenderer(sym))
    # 大图层: 缩放控制
    try:
        cad.setScaleBasedVisibility(True)
        cad.setMinimumScale(250000)   # 缩放 > 1:250000 时隐藏（避免全州视图卡）
        cad.setMaximumScale(0)
    except Exception:
        pass
    proj.addMapLayer(cad); ok.append("NSW地块")
else:
    print("FAIL: NSW 地块")

# ═══ 3. VIC 地块边界 (4.3M) ═══
vic = QgsVectorLayer(
    "/home/yy/qgis-data/vic-cadastre/vic_cadastre_all.gpkg|layername=vic_parcels",
    "VIC 地块边界 (4.3M)", "ogr")
if vic.isValid():
    sym = QgsFillSymbol.createSimple({
        "color": "0,0,0,0",
        "outline_color": "30,144,255,160",   # 蓝色边线（区别 NSW）
        "outline_width": "0.4"
    })
    vic.setRenderer(QgsSingleSymbolRenderer(sym))
    try:
        vic.setScaleBasedVisibility(True)
        vic.setMinimumScale(250000)
        vic.setMaximumScale(0)
    except Exception:
        pass
    proj.addMapLayer(vic); ok.append("VIC地块")
else:
    print("FAIL: VIC 地块")

# ═══ 4. NSW 成交兜底 (50K, 地址级) ═══
geo = QgsVectorLayer(
    "/home/yy/qgis-data/nsw-property-photon-geocoded.gpkg|layername=geocoded",
    "NSW 成交兜底·地址级 (50K)", "ogr")
if geo.isValid():
    cats = [
        QgsRendererCategory("photon",
            QgsMarkerSymbol.createSimple({"name": "circle", "color": "#e31a1c", "size": "3", "outline_style": "no"}),
            "Photon 街道级"),
        QgsRendererCategory("google",
            QgsMarkerSymbol.createSimple({"name": "circle", "color": "#ff7f00", "size": "3", "outline_style": "no"}),
            "Google 精确"),
        QgsRendererCategory("strata_plan_not_in_cadastre",
            QgsMarkerSymbol.createSimple({"name": "circle", "color": "#fdae61", "size": "3", "outline_style": "no"}),
            "Strata 质心"),
        QgsRendererCategory("lot_plan_not_found",
            QgsMarkerSymbol.createSimple({"name": "circle", "color": "#78c679", "size": "3", "outline_style": "no"}),
            "LotPlan 未找到"),
    ]
    geo.setRenderer(QgsCategorizedSymbolRenderer("geocode_source", cats))
    proj.addMapLayer(geo); ok.append("兜底")
else:
    print("FAIL: 兜底")

# ═══ 5. NSW 成交全量 (1.9M, parcel 级) ═══
fin = QgsVectorLayer(
    "/home/yy/qgis-data/nsw-property-matched-final.gpkg|layername=all_matched",
    "NSW 成交·parcel级 (1.9M)", "ogr")
if fin.isValid():
    sym = QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": "35,139,69,255", "size": "1.5", "outline_style": "no"})
    fin.setRenderer(QgsSingleSymbolRenderer(sym))
    proj.addMapLayer(fin); ok.append("成交全量")
else:
    print("FAIL: 成交全量")

# ═══ 6-9. Coffs 专题组 ═══
coffs_layers = [
    ("coffs-harbour/coffs-cadastre-fixed.geojson", "Coffs 地块", None),
    ("coffs-harbour/coffs-property-sales-fixed.geojson", "Coffs 成交", None),
    ("coffs-harbour/coffs-abs-poa-fixed.geojson", "Coffs ABS 邮区", None),
    ("coffs-harbour/coffs-spatial-summary-fixed.geojson", "Coffs 空间汇总", None),
]
for path, name, _ in coffs_layers:
    full = f"/home/yy/qgis-data/{path}"
    l = QgsVectorLayer(full, name, "ogr")
    if l.isValid():
        if "地块" in name:
            sym = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "255,215,0,150", "outline_width": "0.5"})
            l.setRenderer(QgsSingleSymbolRenderer(sym))
        elif "成交" in name:
            sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": "#ffff33", "size": "3", "outline_style": "no"})
            l.setRenderer(QgsSingleSymbolRenderer(sym))
        else:
            sym = QgsFillSymbol.createSimple({"color": "70,130,180,40", "outline_color": "70,130,180,120", "outline_width": "0.3"})
            l.setRenderer(QgsSingleSymbolRenderer(sym))
        proj.addMapLayer(l); ok.append(name)
    else:
        print(f"FAIL: {name}")

# ═══ 写入 + 修补图层树 ═══
path = "/home/yy/qgis-data/au-property-master.qgs"
proj.write(path)
print(f"\nOK layers: {ok}")
print(f"Saved: {path}")
QgsApplication.exitQgis()
