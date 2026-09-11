#!/usr/bin/env bash
# 下载完成后: 重建东南沿海镶嵌 → 山体阴影/等高线 → 重导图层
# 用法: bash scripts/build_band_mosaic.sh <project.qgs> [more.qgs ...]
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
Q=$ROOT/au-terrain
PROJECTS=()
for a in "$@"; do PROJECTS+=("$ROOT/${a#./}"); done

echo "== [1/5] 残留 .part 检查 =="
ls "$ROOT"/dem-test/*.part 2>/dev/null && { echo "下载未完成!"; exit 1; } || true

echo "== [2/5] gdalwarp 全瓦片镶嵌 =="
rm -f "$Q/copdem_30m_mosaic.tif"
gdalwarp "$ROOT"/dem-test/Copernicus_DSM_COG_10_*.tif "$Q/copdem_30m_mosaic.tif" \
  -dstnodata -9999 -co COMPRESS=DEFLATE -co TILED=YES -multi --config GDAL_NUM_THREADS ALL_CPUS >/dev/null
gdalinfo -nomd "$Q/copdem_30m_mosaic.tif" | grep "Size is"
gdaladdo -r average "$Q/copdem_30m_mosaic.tif" 2 4 8 16 32 >/dev/null 2>&1

echo "== [3/5] gdaldem 山体阴影 30m(qgis_process 版有黑块缺陷,实测弃用)=="
rm -f "$Q/hillshade_30m.tif"
gdaldem hillshade -s 111120 -co COMPRESS=DEFLATE -co TILED=YES \
  "$Q/copdem_30m_mosaic.tif" "$Q/hillshade_30m.tif"
gdaladdo -r average "$Q/hillshade_30m.tif" 2 4 8 16 32 >/dev/null 2>&1

echo "== [4/5] 等高线 50m(全带)+ 简化 =="
rm -f "$Q/contours_20m.gpkg"
gdal_contour -a elev -i 50 -f GPKG "$Q/copdem_30m_mosaic.tif" "$Q/contours_50m_raw.gpkg"
ogr2ogr -f GPKG "$Q/contours_20m.gpkg" "$Q/contours_50m_raw.gpkg" contour -simplify 0.00003 -nln contour -update -overwrite
rm -f "$Q/contours_50m_raw.gpkg"
ogrinfo -so -al "$Q/contours_20m.gpkg" 2>/dev/null | grep "Feature Count"

echo "== [5/5] PyQGIS 重导图层 =="
python3 scripts/add_terrain_layers.py "${PROJECTS[@]}" | grep -E "inserted|saved"
python3 scripts/add_population.py --layers-only "${PROJECTS[@]}" | grep -E "saved"
python3 scripts/set_xyz_zoom.py --zmax 20 "${PROJECTS[@]}" | grep -E "saved|updated"
echo "== 完成 =="
