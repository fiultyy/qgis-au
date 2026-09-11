# 澳大利亚官方高程(DEM)数据实测调研 — NSW 重点(Sydney 151.21,-33.86 / Coffs Harbour 153.11,-30.30)

> 全部结论基于 2026-08-28 通过代理 `http://127.0.0.1:7892` 的 curl/gdalinfo 实测。实测代理吞吐:GA S3 ≈ 4.6MB/s,GA CloudFront ≈ 15.6MB/s,NSW Portal ≈ 18–24.6MB/s(远高于预估 0.2–2.5MB/s;但保守按 0.2MB/s 也给出估算)。

---

## TL;DR 推荐

| 层级 | 首选 | 理由(实测) |
|---|---|---|
| ① 底图级 全国 1″(~30m) | **GA SRTM 1s Hydro-Enforced 全国 COG,零下载远程直读** — QGIS 直接加 `/vsizip/vsicurl/https://elevation-direct-downloads.s3-ap-southeast-2.amazonaws.com/1sec-dem/71498.zip/srtm-1sec-demh-v1-COG.tif` | gdalinfo 实测通过;147,600×122,400 @1″ Float32,113–154°E/10–44°S 全国覆盖;COG 按需读,不用下 42GiB |
| ① 备选(本地小体积) | Copernicus GLO-30 S3 瓦片(悉尼 19.9MB/幅, Coffs 4.4MB/幅) | `copernicus-dem-30m.s3.amazonaws.com` 实测 206 可下;非澳洲官方但是 30m 全球公开 |
| ② 精细级 5m LiDAR — **NSW 官方直链** | `https://portal.spatial.nsw.gov.au/download/dem/56/{图幅ID}.zip` → Coffs `CoffsHarbour-DEM-AHD_56_5m.zip`(76.8MB)、Sydney `Sydney-DEM-AHD_56_5m.zip`(146.8MB) | 已实测下载 + gdalinfo + 点位采值(Coffs 5.76m / Sydney CBD 15.44m),覆盖两个重点区,**Sydney CBD 只有这条路直接覆盖**(GA 2008 城市包不含 CBD) |
| ② 精细级 5m 全国拼图(GA) | `5m-dem/national_utm_mosaics/nationalz56_ag.zip`(9.8GiB,单 tif,亦支持远程 COG 直读) | z56 带覆盖 149°31′–153°43′E / 21°57′–37°19′S,同时含 Sydney 与 Coffs;2001–2015 采集拼接(旧于 NSW 官方包) |
| 覆盖索引(QGIS 可加) | ELVIS 瓦片足迹:`https://services2.arcgis.com/Yb2UeNWvQYEwyYDl/arcgis/rest/services/ELVIS_Footprint_Releases/FeatureServer/0`;NSW 图幅索引:`https://portal.spatial.nsw.gov.au/server/rest/services/Hosted/Elevation_Index_Public/FeatureServer/0` | 均实测可查;Coffs 命中 `CoffsHarbour_202306`(2023-06 采集,10ppm,±0.3m 垂直精度);NSW 命中 9130 SYDNEY / 9537 COFFS HARBOUR / 9437 DORRIGO / 9030 PENRITH |

---

## 1. ELVIS(https://elevation.fsdf.org.au)— GA 官方高程门户

### 下载机制(逆向自前端 bundle)
- 新版(2025–26)Angular 前端调用(从 Wayback Machine 存档的 `main-*.js` 提取):
  - `GET https://api.elevation.fsdf.org.au/elevation/downloadables?polygon=POLYGON((...))` → 返回 available_data(各项目/产品可下载树)
  - `POST https://api.elevation.fsdf.org.au/elevation/initiateJob` → 异步打包下载任务(选区打包,非逐瓦片)
  - `GET https://api-elevation.fsdf.org.au/elevation-at-point`、`/elevation/identify`
- 覆盖可视化瓦片:`https://s3-ap-southeast-2.amazonaws.com/fsdf-elevation-tile-cache/{DEM|POINT_CLOUD|IMAGERY|BATHYMETRY}/{z}/{x}/{y}.png`(PNG 图例瓦片,非高程值)
- 旧版(2023)还用 FME:`elvis-ga.fmecloud.com/fmedatastreaming/elvis_indexes/ReturnDownloadables.fmw?polygon=...`

### 实测结果 — **本网络全部被封**
| 端点 | 结果 |
|---|---|
| `api.elevation.fsdf.org.au/*`(含 downloadables/initiateJob) | **403 CloudFront "Request blocked"**(WAF;直连不走代理同样 403;带 Origin/Referer 无效)→ 疑似地域/IP 封锁 |
| `elvis-ga.fmecloud.com/.../ReturnDownloadables.fmw`(带 polygon) | **401 Unauthorized**(已锁) |
| ELVIS 前端 JS 资产(`styles-*.css`、`chunk-*.js`、`/cache/images/*.png`) | 全部回退 SPA index(text/html)→ 站点资产当前 404(Wayback 亦如此),前端源码经 Wayback 2023/2025-09 存档获得 |
| `nsw.elvis` S3 桶(旧 NSW 直链) | **NoSuchBucket**(已删) |

→ **结论:ELVIS 的"选区打包"API 从当前网络不可程序化调用**;QGIS 里走这条路同样会 403。ELVIS 的瓦片足迹 FeatureServer(托管在 Esri `services2.arcgis.com`,不受 GA 封锁)仍可查询/加载。

---

## 2. Geoscience Australia 其他出口

### 2a. ★ 核心发现:`elevation-direct-downloads` S3 直链桶(来自 ecat 元数据 transferOptions)
桶:`https://elevation-direct-downloads.s3-ap-southeast-2.amazonaws.com`(ListBucket 拒绝,但对象 GET/Range 通,206 支持断点)

**1 秒 DEM(SRTM-derived,即 ELVIS 上 "SRTM 1 Second HnDEM")**
| 产品 | key | 实测大小 | 内部结构(远程读 zip 中央目录) |
|---|---|---|---|
| DEM-H 水文加强(推荐) | `1sec-dem/71498.zip` | **45,128,225,630 B = 42.0GiB** | 单文件 `srtm-1sec-demh-v1-COG.tif`(COG)+ Ancillary(DEMS_TileIndex.shp 等) |
| DEM 原始 | `1sec-dem/69816.zip` | 23.5GB(ecat 标称) | 未实测 |
| DEM-S 平滑 | `1sec-dem/70715.zip` | 27GB(ecat 标称) | 未实测 |
| 用户指南 | `1sec-dem/1secSRTM_Derived_DEMs_UserGuide_v1.0.4.pdf` | ~1.3MB | 200 ✓ |

- **QGIS 零下载远程直读(实测通过)**:
  `gdalinfo /vsizip/vsicurl/https://elevation-direct-downloads.s3-ap-southeast-2.amazonaws.com/1sec-dem/71498.zip/srtm-1sec-demh-v1-COG.tif`
  → `GTiff, 147600×122400, Pixel 0.000278°(1″), Float32, UL 112d59'59.5"E 10d0'0.5"S, LR 153d59'59.5"E 44d0'0.5"S, NoData -3.4e38` ✓
- 无按瓦片的 1s 直链(桶内 key 猜测均 403;整包为单 COG)。

**5m LiDAR DEM(全国拼图,ecat 记录 22be4b55-2465-4320-e053-10a3070a5236)**
| key | 大小 | 说明 |
|---|---|---|
| `5m-dem/national_utm_mosaics/nationalz56_ag.zip` | **10,611,021,424 B = 9.8GiB**(实测) | z56(含 NSW 东海岸:Sydney+Coffs);内部单文件 `nationalz56_ag.tif`,**远程 /vsizip/vsicurl/ 直读实测通过**(84,747×339,555 @5m Float32,覆盖 149°31′–153°43′E / 21°57′–37°19′S) |
| `5m-dem/national_utm_mosaics/nationalz55_ag.zip` | 10.8GB(标称) | z55(NSW 西部/VIC/TAS) |
| `5m-dem/national_utm_mosaics/mdbaz56_qg.zip` | 310,639,595 B = 296MB(实测 HEAD) | MDBA z56 子集;Range GET 得合法 ZIP 头 ✓(内陆流域,不含沿海 Sydney/Coffs) |
| `5m-dem/national_utm_mosaics/mdbaz55_qg.zip` / `nationalz54ag.zip` / `mdbaz54_qg.zip` 等 | 2.5–6.1GB | 其他带 |

**5m HDEM 城市包(GA CloudFront,记录 64f9fe76…,实测极快)**
- Base:`https://d28rz98at9flks.cloudfront.net/104740/`
- `SydneyHDEM2008_5m.zip` **67.7MB,4.5s 下完(15.6MB/s)**,内含 `SydneyHDEM2008_5m.tif` 265MB(GDA94 TM z56, 6311×10321 @5m Float32)——**但范围 151°00′–151°21′E / 33°54′–34°03′S,只到 CBD 以南(Kogarah–Royal NP–Wollongong 北),不含 Sydney CBD!**
- 同系列:`HunterCoastHDEM2007_5m.zip` 127.6MB(Newcastle)、Brisbane/GoldCoast/Melbourne/Adelaide/Swan 等;无 Coffs 包。
- 注意此产品采集 2001–2015;**Coffs 5m 的新采集(2023-06)只在 ELVIS/NSW 渠道**。

### 2b. services.ga.gov.au ArcGIS REST / WCS
| 端点 | 结果 |
|---|---|
| `/gis/rest/services/DEM_LiDAR_5m(_2025)/MapServer?f=pjson`、`DEM_SRTM_1Second_Hydro_Enforced_2024/MapServer(/{0,3})`、`.../WCSServer`、`.../WMSServer`、`/gis/rest/services?f=json`、`site_9/rest/services/...` | **全部 403 CloudFront "Request blocked"**(WAF;直连同;gaservices.ga.gov.au 镜像 404) |
| `/gis/rest/services/NationalBaseMap/MapServer?f=pjson` | **200(ArcGIS 10.91)** → 非整站封,是针对 DEM/服务路径的 WAF 规则 |
| `portal.ga.gov.au/proxy/https://services.ga.gov.au/...WCS` | 返回 Portal SPA HTML(代理路径已死) |

→ **QGIS 直接加 GA 的 DEM WCS/ImageServer 在本网络不可用**(其余网络如澳洲本土 IP 可能可用,未验证)。

### 2c. ecat.ga.gov.au / data.gov.au
- **ecat CSW 可用**(`POST /geonetwork/srv/eng/csw` XML,GET GetRecordById)——本文所有 S3 直链即由此获得;OGC-API `/geonetwork/api/collections/main/items` 500(服务器配置错误,勿用)。
- data.gov.au:CKAN `package_show` 404、页面 JS 渲染、新 API 404 → **没拿到 SRTM/5m 的 data.gov.au 直链**(非必需,ecat 直链已覆盖)。

---

## 3. NSW 官方(Spatial Services / SEED)

### 3a. ★ NSW Spatial Collaboration Portal(实测最优精细级来源)
- Portal:`https://portal.spatial.nsw.gov.au`(ArcGIS Enterprise;Sharing REST 9.2,Server 10.91,`/server/rest/services` 可列)
- `services.spatial.nsw.gov.au` = NXDOMAIN(已退役);`maps.six.nsw.gov.au/arcgis/rest` 404。
- **图幅索引层(QGIS 可直接加)**:`https://portal.spatial.nsw.gov.au/server/rest/services/Hosted/Elevation_Index_Public/FeatureServer/0`
  字段含 `mapnumber/maptitle/zone/dems5mid/slope5mid/aspect5mid/contourid`。点选/框选实测命中:
  - 9537 COFFS HARBOUR (z56)、9437 DORRIGO (z56)
  - 9130 SYDNEY (z56)、9030 PENRITH (z56)
- **直链模板**(来自官方 "Elevation Download Map" webmap popup,已验证):
  ```
  https://portal.spatial.nsw.gov.au/download/dem/56/Sydney-DEM-AHD_56_5m.zip       → 153,867,492 B (146.8MB)
  https://portal.spatial.nsw.gov.au/download/dem/56/CoffsHarbour-DEM-AHD_56_5m.zip  →  80,489,990 B (76.8MB)
  https://portal.spatial.nsw.gov.au/download/slope/56/CoffsHarbour-SLP-AHD_56_5m.zip → 78.8MB
  https://portal.spatial.nsw.gov.au/download/aspect/56/Sydney-ASP-AHD_56_5m.zip      → 194.1MB
  https://portal.spatial.nsw.gov.au/download/contours/56/CoffsHarbour-CONT-AHD_56_2m.zip → 73.4MB
  ```
- **实测验证(已下载 + gdalinfo + 采值)**:
  - 格式:ESRI ASCII Grid(`.asc`+`.prj`),GDA94 MGA zone 56(EPSG:28356 等效),5m Float32,NoData -9999
  - **Coffs**:9645×11102 px,范围 153°00′–153°30′E / 30°00′–30°30′S → 覆盖 Coffs 点 ✓;点值 **5.76m**
  - **Sydney**:9452×11247 px,范围 151°00′–151°30′E / 33°29′–34°01′S → **覆盖 Sydney CBD** ✓(151.207,-33.868);点值 **15.44m**
  - 下载速度 18–24.6MB/s(3.3s / 8.5s)
- **矢量等高线(QGIS 可加)**:`NSW_Elevation_and_Depth_Theme_multiCRS/FeatureServer`(SpotHeight/RelativeHeight/Contour 10m/20m 历史等高线);NSW 无公开 DEM 影像服务。

### 3b. SEED
- `datasets.seed.nsw.gov.au/api/3/action/package_search` → **202 反爬挑战**(无 JS 不可用);`data.seed.nsw.gov.au` SSL 失败。SEED 对高程无更好直链,NSW 主渠道就是上面的 Spatial Portal。

---

## 失败清单(全部标注原因)

| 来源/端点 | 状态 | 原因 |
|---|---|---|
| `api.elevation.fsdf.org.au`(ELVIS downloadables/initiateJob/identify) | 403 | CloudFront WAF "Request blocked"(代理与直连均 403) |
| `api-elevation.fsdf.org.au/elevation-at-point` | 403 | 同上 |
| `elvis-ga.fmecloud.com`(ReturnDownloadables/IdentifyProject .fmw) | 401 | FME 已要求认证 |
| ELVIS 前端静态资产(chunk-*.js 等) | 404→SPA index | 部署故障/路径回退(源码取自 Wayback) |
| `services.ga.gov.au` DEM 系列 REST/WMS/WCS | 403 | WAF 按路径封(NationalBaseMap 放行证明非整站) |
| `portal.ga.gov.au/proxy/...` | 200 HTML | 代理路由已死,返回 SPA |
| data.gov.au CKAN/页面 | 404/JS | 平台迁移,API 不可用 |
| ecat OGC-API items | 500 | 服务器配置错误(microservices.url 缺失);CSW 正常 |
| SEED CKAN | 202 | 边缘反爬挑战 |
| `services.spatial.nsw.gov.au` | NXDOMAIN | 已退役 |
| `nsw.elvis` / `dmgaol` S3 桶 | NoSuchBucket | 已删除 |
| 1s 按瓦片直链(桶内猜 key) | 403 | ListBucket 关闭、key 不可枚举(只有整包单 COG) |

---

## 下载量与时间估算

**精细级 5m(推荐 NSW 官方)**
| 项 | 体积(zip) | 本机实测 | 若 0.2MB/s |
|---|---|---|---|
| Coffs DEM 5m(NSW 图幅 9537) | 76.8MB → .asc 解压 ~858MB(建议转 GTiff ~70MB) | 3.3s | ~6.4 min |
| Sydney DEM 5m(NSW 图幅 9130) | 146.8MB → .asc ~1.06GB(GTiff ~120MB) | 8.5s | ~12.2 min |
| GA 全国 z56 5m 拼图(替代) | 9.8GiB | 4.6MB/s ≈ 36 min | ~14 h |
| GA SydneyHDEM2008(仅 CBD 以南) | 67.7MB | 4.5s | ~5.6 min |

**底图级 1″(~30m)**
| 项 | 体积 | 说明 |
|---|---|---|
| SRTM 1s DEM-H 全国 COG **远程直读** | 0(按需 COG 读) | QGIS 加 /vsizip/vsicurl/ 路径;分析仅读所需分块 |
| SRTM 1s DEM-H 整包 | 42.0GiB | 4.6MB/s ≈ 2.6h / 0.2MB/s ≈ 59h |
| Copernicus GLO-30 悉尼幅(S34_00_E151_00) | 19.9MB | 回退项 |
| Copernicus GLO-30 Coffs 幅(S31_00_E153_00) | 4.4MB | 回退项 |

**Coffs 与 Sydney 合计(NSW 官方路线)**:DEM 224MB + 可选 slope/aspect/contours ≈ DEM-only 224MB,全家桶约 690MB。0.2MB/s 最坏 ~1h。

---

## QGIS 操作要点

1. **远程 1″ 底图(零下载)**:Layer → Add Raster Layer,Source 粘贴
   `/vsizip/vsicurl/https://elevation-direct-downloads.s3-ap-southeast-2.amazonaws.com/1sec-dem/71498.zip/srtm-1sec-demh-v1-COG.tif`
   (首次加载会读 zip 中央目录,稍慢;之后按视窗取块。)
2. **NSW 5m**:`curl -x http://127.0.0.1:7892 -O https://portal.spatial.nsw.gov.au/download/dem/56/CoffsHarbour-DEM-AHD_56_5m.zip` 等;解压得 `.asc` 直接可加;建议压转:
   `gdal_translate -co COMPRESS=DEFLATE -co TILED=YES CoffsHarbour-DEM-AHD_56_5m.asc Coffs_5m.tif`(体积 ~10:1)
3. **坐标系**:NSW 包为 GDA94 MGA56(≈EPSG:28356);GA 1s COG 为 WGS84(EPSG:4326)。与 GDA2020(7856)工程叠加时建议挂 NTv2 grid,或统一重投影。
4. **索引图层**:把两个 FeatureServer(ELVIS 足迹 / NSW Elevation_Index_Public)加进工程做覆盖参考。
