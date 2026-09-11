# 澳洲公开 Overlay / GIS 数据源目录

> **用途**: 房产与环境分析，覆盖全澳，优先 NSW/Sydney 区域
> **更新**: 2026-07-24
> **优先级标注**: ⭐⭐⭐ 极高价值 | ⭐⭐ 高价值 | ⭐ 有用

---

## 目录
1. [自然灾害风险](#1-自然灾害风险)
2. [环境保护](#2-环境保护)
3. [规划/用地](#3-规划用地)
4. [人口统计](#4-人口统计)
5. [基础设施](#5-基础设施)
6. [已下载数据清单](#6-已下载数据清单)
7. [关键平台汇总](#7-关键平台汇总)

---

## 1. 自然灾害风险

### 1.1 洪水 Flood Overlay ⭐⭐⭐

#### NSW
| 项目 | 详情 |
|------|------|
| **数据源** | NSW Flood Data Portal (via SEED) |
| **URL** | https://www.environment.nsw.gov.au/topics/water/floodplains/nsw-flood-data-portal |
| **SEED Portal** | https://datasets.seed.nsw.gov.au/ |
| **费用** | 免费 |
| **格式** | Shapefile, WMS, ArcGIS REST |
| **覆盖** | NSW 全州 (逐步覆盖中,由各 Council 上传) |
| **更新** | 滚动更新 (Council 上传后发布) |
| **批量下载** | ✅ 可通过 SEED portal 批量下载 |
| **备注** | NSW SES + DCCEEW 联合管理;洪水研究、洪水风险图、洪水规划区 |

| 项目 | 详情 |
|------|------|
| **数据源** | NSW Planning Portal - Flood Planning Layer (EPI) |
| **URL** | https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/Planning/Hazard/MapServer |
| **费用** | 免费 |
| **格式** | WMS, ArcGIS REST MapServer (Layer 1 = Flood Planning) |
| **覆盖** | NSW 全州 |
| **更新** | 随规划修编更新 |
| **批量下载** | WMS 可直接接入 QGIS;数据量巨大不建议全量导出 |
| **QGIS 接入** | Add Layer → WMS → URL 填入上述 MapServer |

#### 全澳
| 项目 | 详情 |
|------|------|
| **数据源** | Australian Flood Risk Information Portal (AFRIP) |
| **URL** | https://www.ga.gov.au/scientific-topics/community-safety/projects/afrip |
| **费用** | 免费 |
| **格式** | Web map, 部分可下载 |
| **覆盖** | 全澳 (快照至 2018 年) |
| **更新** | 维护为 2018 快照,不再更新 |
| **批量下载** | ⚠️ 有限,主要为在线查询 |

#### VIC
| 项目 | 详情 |
|------|------|
| **数据源** | DEECA Flood Mapping / Vicmap Planning |
| **URL** | https://discover.data.vic.gov.au/dataset/vicmap-planning |
| **费用** | 免费 |
| **格式** | Shapefile, WFS, WMS |
| **覆盖** | VIC 全州 |
| **更新** | 持续更新 (Vicmap Planning 实时同步规划方案) |
| **批量下载** | ✅ data.vic.gov.au 提供 |

---

### 1.2 山火 Bushfire Prone Land / BAL ⭐⭐⭐

#### NSW
| 项目 | 详情 |
|------|------|
| **数据源** | NSW Rural Fire Service (RFS) - Bush Fire Prone Land |
| **Data.NSW** | https://data.nsw.gov.au/data/dataset/nsw-bush-fire-prone-land |
| **Spatial Portal** | https://portal.spatial.nsw.gov.au/portal/home/item.html?id=84c338fe2e8c49a9836751ed49c9c581 |
| **费用** | 免费 |
| **格式** | ArcGIS Feature Layer, WMS, WFS |
| **覆盖** | NSW 全州 (所有 LGA) |
| **更新** | 每次 LGA 认证后更新 (滚动) |
| **批量下载** | ✅ 可通过 Spatial NSW Portal 下载 Shapefile/GeoJSON |
| **数据分类** | Vegetation Category 1 (高风险森林), 2 (雨林低风险), 3 (草地湿地) + 100m/30m Buffer |
| **QGIS 接入** | 直接添加 ArcGIS REST FeatureServer |

#### VIC
| 项目 | 详情 |
|------|------|
| **数据源** | Bushfire Management Overlay (BMO) - via Vicmap Planning |
| **URL** | https://discover.data.vic.gov.au/dataset/vicmap-planning |
| **费用** | 免费 |
| **格式** | Shapefile, WFS |
| **覆盖** | VIC 全州 |
| **更新** | 持续 |
| **批量下载** | ✅ |

#### 全澳
| 项目 | 详情 |
|------|------|
| **数据源** | AFAC (Australasian Fire and Emergency Service Authorities Council) |
| **URL** | https://www.afac.com.au/ |
| **费用** | 部分免费 |
| **备注** | 主要为政策协调,具体 GIS 数据需从各州获取 |

---

### 1.3 海岸侵蚀 Coastal Hazard ⭐⭐

| 项目 | 详情 |
|------|------|
| **数据源 (NSW)** | NSW Coastal Erosion and Inundation Assessment 2025 |
| **URL** | https://www.climatechange.environment.nsw.gov.au/resources-and-research/sea-level-rise-and-coastal-hazards |
| **费用** | 免费 (报告 + 部分空间数据) |
| **格式** | PDF 报告, 部分GIS 数据 |
| **覆盖** | NSW 全海岸线 |
| **更新** | 2025 最新评估 |

| 项目 | 详情 |
|------|------|
| **数据源 (QLD)** | QLD Coastal Hazard Area Maps |
| **URL** | https://www.qld.gov.au/environment/coasts-waterways/coast-hazards/coastal-hazards-and-mapping |
| **费用** | 免费 |
| **格式** | PDF 地图, 可请求 GIS 数据 |
| **覆盖** | QLD 海岸线 |
| **批量下载** | ⚠️ 需通过 map request 工具逐张获取 |

| 项目 | 详情 |
|------|------|
| **数据源 (QLD)** | Brisbane City Plan - Coastal Hazard Overlay |
| **URL** | https://www.data.qld.gov.au/dataset/cp14-coastal-hazard-overlay-coastal-erosion |
| **费用** | 免费 |
| **格式** | Shapefile, GeoJSON, KML |
| **批量下载** | ✅ |

---

### 1.4 滑坡 Landslide Risk ⭐⭐

| 项目 | 详情 |
|------|------|
| **数据源** | NSW EPI - Landslide Risk |
| **Data.NSW** | https://data.nsw.gov.au/data/dataset/epi-landslide-risk |
| **NSW Planning** | https://www.planningportal.nsw.gov.au/opendata/dataset/epi-landslide-risk |
| **费用** | 免费 |
| **格式** | WMS, ArcGIS REST MapServer (Layer 2 = Landslide Risk Land) |
| **URL** | https://mapprod3.environment.nsw.gov.au/arcgis/services/Planning/Hazard/MapServer/ |
| **覆盖** | NSW 特定区域 (坡度风险区) |
| **更新** | 随规划修编 |
| **批量下载** | WMS 接入 QGIS |
| **QGIS 接入** | Add Layer → WMS → 同 Flood Planning 同一 MapServer |

---

## 2. 环境保护

### 2.1 遗产 Heritage Overlay ⭐⭐⭐

#### NSW
| 项目 | 详情 |
|------|------|
| **数据源** | NSW State Heritage Register Curtilages |
| **SEED** | https://datasets.seed.nsw.gov.au/dataset/state-heritage-register-curtilages1c5ee |
| **ArcGIS** | https://www.arcgis.com/home/item.html?id=2fdf89c8d6394d53b85085e896bc048b |
| **费用** | 免费 |
| **格式** | Shapefile, ArcGIS Feature Layer |
| **覆盖** | NSW 全州 |
| **更新** | 随注册更新 |
| **批量下载** | ✅ SEED portal 下载 |

| 项目 | 详情 |
|------|------|
| **数据源** | NSW State Heritage Inventory (含 Local + State) |
| **URL** | https://www.environment.nsw.gov.au/topics/heritage/resources/search-heritage-databases/state-heritage-inventory |
| **费用** | 免费 |
| **格式** | 在线搜索 + 空间查看器 (30,000+ 条记录) |
| **批量下载** | ⚠️ 主要为在线查询,部分数据可通过 SEED 获取 |

#### 全澳
| 项目 | 详情 |
|------|------|
| **数据源** | National Heritage List / Commonwealth Heritage List |
| **URL** | https://www.dcceew.gov.au/parks-heritage/heritage/places/national |
| **费用** | 免费 |
| **格式** | 在线数据库, 部分 GIS |
| **批量下载** | ⚠️ 有限 |

---

### 2.2 受污染土地 Contaminated Land ⭐⭐⭐

#### NSW
| 项目 | 详情 |
|------|------|
| **数据源** | NSW EPA - Contaminated Land Record of Notices |
| **URL** | https://app.epa.nsw.gov.au/prclmapp/searchregister.aspx |
| **List of Notified Sites** | https://www.epa.nsw.gov.au/Your-environment/Contaminated-land/notified-and-regulated-contaminated-land/list-of-notified-sites |
| **费用** | 免费 |
| **格式** | 在线搜索数据库 + 月度 PDF/XLSX 列表 |
| **覆盖** | NSW 全州 |
| **更新** | 每月更新 |
| **批量下载** | ⚠️ PDF/XLSX 列表可下载, 但无原生 GIS 格式;需地理编码 |
| **备注** | 包含 "significantly contaminated" 声明场地 + 已通知场地 |

---

### 2.3 生物多样性 Biodiversity Values Map ⭐⭐

#### NSW
| 项目 | 详情 |
|------|------|
| **数据源** | NSW Biodiversity Values (BV) Map ("Purple Map") |
| **URL** | https://www.environment.nsw.gov.au/topics/animals-and-plants/biodiversity-offsets-scheme/clear-and-develop-land/biodiversity-values-map-and-threshold-tool |
| **在线工具** | https://www.lmbc.nsw.gov.au/Maps/index.html?viewer=BOSETMap |
| **data.gov.au** | https://data.gov.au/data/dataset/nsw-biodiversity-values-map |
| **费用** | 免费 |
| **格式** | 在线查看器, 部分 WMS |
| **覆盖** | NSW 全州 |
| **更新** | 版本更新 (当前 Version 3+) |
| **批量下载** | ⚠️ 主要为在线查看器; data.gov.au 可能提供部分数据 |
| **触发** | 紫色区域开发需 Biodiversity Development Assessment Report (BDAR) |

---

## 3. 规划/用地

### 3.1 分区 Zoning Overlays ⭐⭐⭐

#### NSW
| 项目 | 详情 |
|------|------|
| **数据源** | NSW Planning Portal Spatial Viewer |
| **URL** | https://www.planningportal.nsw.gov.au/spatialviewer |
| **Open Data** | https://www.planningportal.nsw.gov.au/opendata/dataset |
| **费用** | 免费 |
| **格式** | WMS, WFS, ArcGIS REST (216+ 数据集) |
| **覆盖** | NSW 全州 |
| **更新** | 持续更新 |
| **分区类型** | R1/R2/R3 (住宅), B1-B8 (商业), IN1-IN4 (工业), RU1/RU2/RU4 (农村), E1-E4 (环境管理), SP1-SP3 (特殊用途) 等 |
| **批量下载** | ✅ 通过 Open Data Portal 可获取 |
| **QGIS 接入** | 直接添加 WMS/WFS 服务 |

#### VIC
| 项目 | 详情 |
|------|------|
| **数据源** | Vicmap Planning (Zones + Overlays) |
| **URL** | https://discover.data.vic.gov.au/dataset/vicmap-planning |
| **费用** | 免费 |
| **格式** | Shapefile, WFS, WMS, GeoPackage |
| **覆盖** | VIC 全州 (79 LGA + 3 其他区域) |
| **更新** | 持续更新 (实时同步规划方案) |
| **批量下载** | ✅ 完整可下载 |
| **数据集包含** | VMPLAN_PLAN_ZONE (分区), VMPLAN_PLAN_OVERLAY (覆盖层,含洪水/山火/遗产等) |

---

### 3.2 交通走廊 Rail/Transport Corridors ⭐⭐

#### NSW
| 项目 | 详情 |
|------|------|
| **数据源** | Transport for NSW Open Data Hub |
| **URL** | https://opendata.transport.nsw.gov.au |
| **费用** | 免费 (需注册账号) |
| **格式** | API (GTFS, REST), Shapefile, CSV, GeoJSON |
| **覆盖** | NSW 全州 |
| **更新** | 实时/定期 |
| **数据集** | 1000+ 数据集包括: 公共交通站点/线路, 实时位置, 路网, 停车, 船舶 |
| **批量下载** | ✅ |

| 项目 | 详情 |
|------|------|
| **数据源** | Interim and Future Transport Corridors |
| **URL** | https://www.transport.nsw.gov.au/operations/roads-and-waterways/business-and-industry/partners-and-suppliers/private-development-0-3 |
| **费用** | 免费 |
| **格式** | 在线地图参考 + 部分空间数据 |
| **覆盖** | Sydney 区域 (未来走廊) |
| **关键走廊** | Interim Rail Corridor, Outer Sydney Orbital, North South Rail Link, East West Rail Link, Western Sydney Freight Line |

#### 全澳
| 项目 | 详情 |
|------|------|
| **数据源** | Digital Atlas of Australia - Railway Lines |
| **URL** | https://digital.atlas.gov.au/datasets/digitalatlas::railway-lines/about |
| **费用** | 免费 |
| **格式** | ArcGIS REST, Shapefile |
| **覆盖** | 全澳 |

---

### 3.3 飞机噪音 ANEF ⭐⭐

| 项目 | 详情 |
|------|------|
| **数据源** | Airservices Australia - ANEF/ANEI |
| **URL** | https://www.airservicesaustralia.com/industry-info/anefs-and-aneis |
| **WebTrak** | https://www.airservicesaustralia.com/community/environment/aircraft-noise/webtrak |
| **费用** | 免费 (在线查看); ANEF 地图通常包含在机场 Master Plan 中 |
| **格式** | 在线地图, PDF 地图, 部分可通过请求获取 GIS |
| **覆盖** | 全澳主要机场 (Sydney, Melbourne, Brisbane, Perth, Adelaide 等) |
| **更新** | 随机场 Master Plan 更新 (通常每 5 年) |
| **批量下载** | ❌ 无批量 GIS 下载;需逐机场获取 |
| **替代方案** | 各机场 Master Plan PDF 包含 ANEF 等值线图 |
| **备注** | ANEF = Australian Noise Exposure Forecast (规划用途); ANEI = Index (历史实际) |

---

## 4. 人口统计

### 4.1 ABS Census 2021 ⭐⭐⭐

#### Census DataPacks (最全数据)
| 项目 | 详情 |
|------|------|
| **数据源** | ABS Census DataPacks |
| **URL** | https://www.abs.gov.au/census/find-census-data/datapacks |
| **费用** | 免费 |
| **格式** | CSV (短标题格式) |
| **地理层级** | Australia → State → SA4 → SA3 → SA2 → SA1 → LGA → Mesh Block |
| **覆盖** | 全澳 |
| **Profile 类型** | General Community Profile (GCP), Aboriginal & Torres Strait Islander, Time Series |
| **数据内容** | 人口, 年龄, 性别, 家庭构成, 收入, 职业, 教育, 语言, 宗教, 住房, 交通方式等 |
| **批量下载** | ✅ 按州/地理层级打包 ZIP |

#### GeoPackages (数据+边界合一)
| 项目 | 详情 |
|------|------|
| **URL** | https://www.abs.gov.au/census/guide-census-data/about-census-tools/geopackages |
| **格式** | GeoPackage (.gpkg) — 数据+空间边界合一 |
| **内容** | 2016/2021 对比, 多种 Profile tables |

#### 数字边界文件
| 项目 | 详情 |
|------|------|
| **URL** | https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/digital-boundary-files |
| **格式** | Shapefile, GeoPackage, GDA2020 & GDA94 |
| **边界类型** | Mesh Block, SA1, SA2, SA3, SA4, GCCSA, LGA, Indigenous Areas, Electoral Divisions 等 |
| **批量下载** | ✅ |

#### ABS Data API
| 项目 | 详情 |
|------|------|
| **URL** | https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/data-services-and-apis |
| **格式** | ArcGIS REST, WMS, WFS |
| **费用** | 免费 |
| **备注** | 无需下载,直接 QGIS 接入 |

#### ABS ArcGIS Online
| 项目 | 详情 |
|------|------|
| **URL** | https://services1.arcgis.com/vHnIGBHHqDR6y0CR/arcgis/rest/services/2021_ABS_General_Community_Profile/FeatureServer |
| **格式** | ArcGIS Feature Layer (SA1 + SA2) |
| **费用** | 免费 |
| **QGIS 接入** | 直接添加 ArcGIS Feature Server |

### 4.2 Digital Atlas of Australia ⭐⭐

| 项目 | 详情 |
|------|------|
| **URL** | https://digital.atlas.gov.au/ |
| **费用** | 免费 |
| **格式** | ArcGIS REST, WMS, 可下载数据集 |
| **覆盖** | 全澳 |
| **数据类型** | 人口预测, 社会经济指标, 基础设施, 环境数据 |
| **批量下载** | ✅ 搜索 "ABS" 标签可获取大量数据集 |

---

## 5. 基础设施

### 5.1 学校学区 School Catchment Zones ⭐⭐⭐

#### NSW
| 项目 | 详情 |
|------|------|
| **数据源** | NSW Department of Education - School Intake Zones |
| **Data.NSW** | https://data.nsw.gov.au/data/dataset/nsw-education-school-intake-zones-catchment-areas-for-nsw-government-schools |
| **费用** | 免费 (CC-BY) |
| **格式** | Shapefile (ZIP) |
| **覆盖** | NSW 全州 (公立学校) |
| **更新** | 每日更新 (通过 School Finder 工具) |
| **批量下载** | ✅ 已下载 → `nsw-school-catchments.zip` |
| **数据包含** | catchments_primary, catchments_secondary, catchments_future, catchments_level (含 .shp/.dbf/.prj/.shx) |

#### 全澳其他州
| 州 | 数据源 |
|----|--------|
| VIC | https://www.findmyschool.vic.gov.au/ (在线工具, 部分可通过 DEECA 获取) |
| QLD | https://www.qld.gov.au/education/schools/finder (在线工具) |
| WA | School intake area maps via WA Department of Education |

---

### 5.2 医院位置 Hospitals ⭐⭐

| 项目 | 详情 |
|------|------|
| **数据源** | Geoscience Australia - National HealthDirect Health Facilities |
| **ArcGIS REST** | https://services.ga.gov.au/gis/rest/services/National_HealthDirect_Health_Facilities/MapServer |
| **费用** | 免费 |
| **格式** | ArcGIS MapServer (GP, Hospitals, Pharmacies) |
| **覆盖** | 全澳 |
| **更新** | 定期 |
| **QGIS 接入** | Add Layer → ArcGIS MapServer |

| 项目 | 详情 |
|------|------|
| **数据源** | Declared Public Hospitals |
| **Digital Atlas** | https://digital.atlas.gov.au/datasets/digitalatlas::declared-public-hospitals/about |
| **ArcGIS Online** | https://www.arcgis.com/home/item.html?id=b3508543bfcc4f60a2430bcf45375cf3 |
| **费用** | 免费 |
| **格式** | Feature Layer |
| **覆盖** | 全澳 |
| **数据来源** | Australian Government Dept of Health, Disability and Ageing |

---

### 5.3 公共交通 Public Transport ⭐⭐

#### NSW
| 项目 | 详情 |
|------|------|
| **数据源** | Transport for NSW Open Data Hub |
| **URL** | https://opendata.transport.nsw.gov.au |
| **费用** | 免费 (需注册) |
| **格式** | GTFS (静态+实时), API, Shapefile |
| **关键数据集** | GTFS bundle (所有运营商站点/线路/时刻表), 站点位置, 实时位置 |
| **更新** | GTFS 静态每季度; 实时 API 持续 |
| **批量下载** | ✅ GTFS bundle ZIP 下载 |

#### 全澳
| 项目 | 详情 |
|------|------|
| **数据源** | Digital Atlas of Australia - Transport |
| **URL** | https://digital.atlas.gov.au/ |
| **格式** | ArcGIS REST, WMS |
| **数据集** | Railway lines, stations, road network |

---

## 6. 已下载数据清单

以下数据已成功下载至 `/home/yy/qgis-data/overlays/`:

| 文件 | 大小 | 内容 | 来源 |
|------|------|------|------|
| `abs-sa1-2021-shapefile.zip` | 96 MB | ASGS SA1 边界 Shapefile (GDA2020) | abs.gov.au |
| `abs-2021-gcp-nsw-sa1.zip` | 119 MB | 2021 Census GCP 数据 (NSW, SA1 级, 129 CSV 文件) | abs.gov.au |
| `nsw-lga-gda2020.zip` | 20 MB | NSW LGA 行政边界 Shapefile (GDA2020) | data.gov.au |
| `nsw-school-catchments.zip` | 8 MB | NSW 公立学校招生区域 Shapefile (primary/secondary/future) | data.nsw.gov.au |

### 需通过 WMS/WFS 在线接入的数据 (无需本地下载)
- **NSW Flood Planning**: `https://mapprod3.environment.nsw.gov.au/arcgis/services/Planning/Hazard/MapServer/`
- **NSW Bushfire Prone Land**: 通过 Spatial NSW Portal ArcGIS FeatureServer
- **NSW Landslide Risk**: 同 Flood Planning MapServer (Layer 2)
- **NSW Planning Zones**: 通过 NSW Planning Portal WMS
- **ABS Census boundaries**: 通过 ABS ArcGIS REST Services
- **National Health Facilities**: 通过 GA ArcGIS MapServer

---

## 7. 关键平台汇总

### 数据门户总表

| 平台 | URL | 覆盖 | 主要数据 |
|------|-----|------|----------|
| **Data.gov.au** | https://data.gov.au | 全澳 | 所有联邦+州政府数据 (LGA 边界, 环境, 基础设施) |
| **Data.NSW** | https://data.nsw.gov.au | NSW | Bushfire, school catchments, EPI layers |
| **SEED NSW** | https://datasets.seed.nsw.gov.au | NSW | 环境/遗产/洪水数据 |
| **NSW Planning Portal Open Data** | https://www.planningportal.nsw.gov.au/opendata/dataset | NSW | 216+ 规划数据集 (分区, EPI, 土地用途) |
| **NSW Spatial Portal** | https://portal.spatial.nsw.gov.au | NSW | Cadastre, bushfire, 影像, 地形 |
| **Transport for NSW Open Data** | https://opendata.transport.nsw.gov.au | NSW | 交通/公交/路网 |
| **Discover Data VIC** | https://discover.data.vic.gov.au | VIC | Vicmap Planning (zones+overlays) |
| **Data QLD** | https://www.data.qld.gov.au | QLD | Coastal hazards, planning schemes |
| **ABS** | https://www.abs.gov.au | 全澳 | Census, ASGS boundaries, 人口经济数据 |
| **Digital Atlas of Australia** | https://digital.atlas.gov.au | 全澳 | 统一门户: 人口/基础设施/环境/交通 |
| **Geoscience Australia** | https://www.ga.gov.au | 全澳 | 地质, 洪水, 卫星影像, 基础设施 |
| **NSW EPA** | https://www.epa.nsw.gov.au | NSW | 受污染土地, 废物管理, 环境监管 |
| **Airservices Australia** | https://www.airservicesaustralia.com | 全澳 | 飞行路径, 噪音监测, ANEF |
| **AdaptNSW** | https://www.climatechange.environment.nsw.gov.au | NSW | 海平面上升, 海岸侵蚀, 气候变化 |

### 推荐优先获取路线 (房产分析)

1. **第一步**: 接入 NSW Planning Portal WMS → 获取分区 + 所有 EPI overlay
2. **第二步**: 接入 NSW Hazard MapServer → 洪水 + 滑坡 (同一服务)
3. **第三步**: 下载 NSW Bushfire Prone Land → ArcGIS FeatureServer
4. **第四步**: 用已下载的 ABS Census DataPack + SA1 边界 → 生成人口热力图
5. **第五步**: 叠加 School Catchments (已下载) + Transport GTFS
6. **第六步**: 查询 EPA Contaminated Land Register → 补充环境风险

---

*本文档基于公开信息整理,数据可用性可能随时变化。建议定期验证链接有效性。*
