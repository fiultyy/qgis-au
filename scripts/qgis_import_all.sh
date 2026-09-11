#!/usr/bin/env bash
# =============================================================
# QGIS 官方通道导入管线(唯一入口,幂等可重跑)
#   产品生成: qgis_process(QGIS 官方 CLI);等高线用原生 gdal_contour
#             + native:simplifygeometries 简化(保持 layername=contour)
#   工程导入: PyQGIS headless(QGIS 官方 Python API),零 XML/SQLite 手术
#
# 用法: bash scripts/qgis_import_all.sh <project.qgs> [more.qgs ...]
# =============================================================
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
Q=$ROOT/au-terrain
N5=$Q/nsw5m
PROJECTS=()
for a in "$@"; do PROJECTS+=("$ROOT/${a#./}"); done

echo "== [0/6] gdalwarp — 东南沿海 DEM 镶嵌(dem-test 全部瓦片)=="
rm -f "$Q/copdem_30m_mosaic.tif"
gdalwarp "$ROOT"/dem-test/Copernicus_DSM_COG_10_*.tif "$Q/copdem_30m_mosaic.tif" \
  -dstnodata -9999 -co COMPRESS=DEFLATE -co TILED=YES -multi >/dev/null
gdaladdo -r average "$Q/copdem_30m_mosaic.tif" 2 4 8 16 >/dev/null 2>&1

echo "== [1/6] gdaldem 山体阴影 — 30m 镶嵌 =="
rm -f "$Q/hillshade_30m.tif"
gdaldem hillshade -s 111120 -co COMPRESS=DEFLATE -co TILED=YES \
  "$Q/copdem_30m_mosaic.tif" "$Q/hillshade_30m.tif"
gdaladdo -r average "$Q/hillshade_30m.tif" 2 4 8 16 >/dev/null 2>&1

echo "== [3/6] 等高线 20m / 5m(gdal_contour + native:simplifygeometries)=="
[ -f "$Q/contours_20m.gpkg" ] || \
  gdal_contour -a elev -i 20 -f GPKG "$Q/copdem_30m_mosaic.tif" "$Q/contours_20m.gpkg"
[ -f "$N5/contours_5m_coffs_s.gpkg" ] || {
  gdal_contour -a elev -i 5 -f GPKG "$N5/CoffsHarbour-DEM-AHD_56_5m.tif" "$N5/contours_5m_coffs_raw.gpkg"
  qgis_process run native:simplifygeometries --INPUT="$N5/contours_5m_coffs_raw.gpkg" \
    --TOLERANCE=1.5 --OUTPUT="$N5/contours_5m_coffs_s.gpkg" >/dev/null
  rm -f "$N5/contours_5m_coffs_raw.gpkg"
}
[ -f "$N5/contours_5m_syd_s.gpkg" ] || {
  gdal_contour -a elev -i 5 -f GPKG "$N5/Sydney-DEM-AHD_56_5m.tif" "$N5/contours_5m_syd_raw.gpkg"
  qgis_process run native:simplifygeometries --INPUT="$N5/contours_5m_syd_raw.gpkg" \
    --TOLERANCE=1.5 --OUTPUT="$N5/contours_5m_syd_s.gpkg" >/dev/null
  rm -f "$N5/contours_5m_syd_raw.gpkg"
}

echo "== [4/6] PyQGIS: 行政区划层 + 人口字段(官方 provider 写入)=="
for p in "${PROJECTS[@]}"; do
  python3 scripts/add_admin_layers.py "$p" | grep -E "inserted|saved" || true
done
python3 scripts/add_population.py --fields-only

echo "== [5/6] PyQGIS: 人口密度层 + 地形层(30m / 5m 精细;逐工程单进程)=="
for p in "${PROJECTS[@]}"; do
  python3 scripts/add_population.py --layers-only "$p" | grep -E "saved"
  python3 scripts/add_terrain_layers.py "$p" | grep -E "inserted|saved"
  done

echo "== [6/6] PyQGIS: XYZ 底图 zmax=20(官方 API,替代曾经的 sed 手术)=="
python3 scripts/set_xyz_zoom.py --zmax 20 "${PROJECTS[@]}"

echo "== 管线完成 =="
