#!/usr/bin/env python3
"""生成 nsw-final.qgs — 最新全量数据工程 v2"""
from qgis.core import (
    QgsApplication, QgsProject, QgsVectorLayer, QgsRasterLayer,
    QgsCoordinateReferenceSystem, QgsMarkerSymbol,
    QgsCategorizedSymbolRenderer, QgsRendererCategory,
    QgsSingleSymbolRenderer,
)

QgsApplication.setPrefixPath("/usr", True)
app = QgsApplication([], False)
QgsApplication.initQgis()

proj = QgsProject.instance()
proj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

ok, fail = [], []

# 1. 本地瓦片底图 — XYZ 方式
tiles = QgsRasterLayer(
    "type=xyz&url=http://127.0.0.1:8088/{z}/{x}/{y}.png&zmax=14&zmin=0",
    "Local Tiles z0-14", "wms")
(tiles.isValid() and (proj.addMapLayer(tiles), ok.append("tiles"))) or fail.append("tiles")

# 2. geocoded 兜底 — 按 source 分类
geo = QgsVectorLayer("/home/yy/qgis-data/nsw-property-photon-geocoded.gpkg",
                     "NSW Geocoded 兜底 (50,043)", "ogr")
if geo.isValid():
    cats = [
        QgsRendererCategory("photon",
            QgsMarkerSymbol.createSimple({"name": "circle", "color": "#e31a1c", "size": "3"}),
            "Photon 街道级"),
        QgsRendererCategory("google",
            QgsMarkerSymbol.createSimple({"name": "circle", "color": "#ff7f00", "size": "3"}),
            "Google 补救"),
        QgsRendererCategory("strata_plan_not_in_cadastre",
            QgsMarkerSymbol.createSimple({"name": "circle", "color": "#fdae61", "size": "3"}),
            "Strata 质心"),
        QgsRendererCategory("lot_plan_not_found",
            QgsMarkerSymbol.createSimple({"name": "circle", "color": "#78c679", "size": "3"}),
            "LotPlan 未找到"),
    ]
    geo.setRenderer(QgsCategorizedSymbolRenderer("geocode_source", cats))
    proj.addMapLayer(geo)
    ok.append("geocoded")
else:
    fail.append("geocoded")

# 3. matched-final — 1.9M parcel 级，绿色小点
fin = QgsVectorLayer(
    "/home/yy/qgis-data/nsw-property-matched-final.gpkg|layername=all_matched",
    "NSW Matched Final (parcel级 全量)", "ogr")
if fin.isValid():
    sym = QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": "35,139,69,120", "size": "2", "outline_style": "no"})
    fin.setRenderer(QgsSingleSymbolRenderer(sym))
    proj.addMapLayer(fin)
    ok.append("final")
else:
    fail.append("final")

proj.write("/home/yy/qgis-data/nsw-final.qgs")
print(f"OK: {ok}")
print(f"FAIL: {fail}")
print("Saved: /home/yy/qgis-data/nsw-final.qgs")
QgsApplication.exitQgis()
