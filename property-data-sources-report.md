# 全澳各州房产数据源调研报告

> 调研日期: 2026-07-24
> 目的: 全澳房产数据采集系统 — 各州房产成交数据 & 地籍数据开放情况

---

## 总览对比表

| 州 | 免费成交数据 | 免费地籍数据 | API | 覆盖范围 | 更新频率 |
|------|:---:|:---:|:---:|:---:|:---:|
| **NSW** | ✅ CSV下载 | ✅ ArcGIS REST | ✅ Cadastre API | 全州 | 每周/按需 |
| **VIC** | ⚠️ 仅中位数统计 | ⚠️ Vicmap付费 | ✅ DataVic CKAN API | 全州 | 季度/年度 |
| **QLD** | ❌ 无免费逐笔数据 | ✅ CC-BY免费下载 | ✅ WMS / QSpatial | 全州 | 持续更新 |
| **WA** | ❌ 付费(Landgate) | ⚠️ SLIP账户付费 | ⚠️ 需协议 | 全州 | 每周/按需 |
| **SA** | ⚠️ 仅中位数统计 | ❌ 付费($250+) | ✅ data.sa CKAN API | 全州 | 季度 |
| **TAS** | ❌ 付费($31/报告) | ✅ LISTdata免费下载 | ✅ LISTservices REST | 全州 | 持续/每半年 |
| **NT** | ❌ 无免费公开数据 | ❌ 需数据协议 | ❌ 无公开API | 全NT | 持续 |
| **ACT** | ⚠️ 仅统计报告 | ✅ ACTmapi免费下载 | ✅ ArcGIS REST / WMS | 全ACT | 持续 |

---

## 详细说明

### 1. VIC — Land Victoria

**主管机构**: Department of Transport and Planning (DTP) / Valuer-General Victoria (VGV)
**门户**: https://www.land.vic.gov.au/
**开放数据门户**: https://www.data.vic.gov.au/
**API 目录**: https://www.developer.vic.gov.au/api-catalogue

#### 房产成交数据
- **免费数据**: ⚠️ **仅有中位数统计，无逐笔成交记录**
- **数据内容**: 按行政区(suburb)分类的房屋/单元/空地中位价
- **格式**: XLS, XLSX
- **历史数据**: 10年年度数据 + 15个月季度数据
- **URL**:
  - 年度: https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics
  - DataVic: https://discover.data.vic.gov.au/dataset?groups=planning
  - 包含数据集:
    - Victorian Property Sales Report - Median House by Suburb Quarterly
    - Victorian Property Sales Report - Median Unit by Suburb Quarterly
    - Victorian Property Sales Report - Median Vacant Land by Suburb Quarterly
    - Victorian Property Sales Report - Time Series
    - Victorian Property Sales Report - Yearly Summary
- **更新频率**: 季度(每年3/6/9/12月)
- **逐笔成交**: 需通过 LANDATA® 购买 Property Sales History and Valuation Reports（付费）
  - https://www.landata.online

#### 地籍/地块数据
- **免费**: ⚠️ **Vicmap Property 为付费产品**
- **数据内容**: 全州 cadastral map base，含 parcel polygons、lot/plan numbers、Crown description、LGA 等
- **格式**: ESRI Geodatabase
- **产品名**: Vicmap Property
- **获取方式**: 通过 data.vic.gov.au 发现元数据，实际数据需购买许可
- **开放数据替代**: LASSI (Land & Survey Spatial Information) 提供在线查看但不提供批量下载
  - https://www.landata.vic.gov.au/lassi

#### API
- **DataVic CKAN API** (v1.2.0, REST) — 可搜索数据集元数据
- **DataVic Open Data API** (v2.1.0, REST) — 可下载开放数据集
- **DeveloperVic Catalogue API** — 开发者门户
- **限制**: 免费API仅提供已开放的数据集（即中位数统计），不含逐笔交易

#### 覆盖范围
- 全维州 79 个 municipalities

---

### 2. QLD — Department of Resources

**主管机构**: Department of Resources / Titles Queensland
**开放数据门户**: https://www.data.qld.gov.au/
**空间数据门户**: QSpatial — https://www.business.qld.gov.au/running-business/support-services/mapping-data-imagery/data/qspatial
**在线地图**: Queensland Globe

#### 房产成交数据
- **免费数据**: ❌ **无免费逐笔成交数据**
- **情况**: QLD 的逐笔销售数据存储在 QVAS (Queensland Valuation and Automation System) 数据库中
- **价格**: 商业定价（用户反馈 $20,000+ 用于数据提取）
- **可免费查看**: 仅可在 Queensland Globe 上查看**地价估值**(land valuation)，非成交价
  - https://www.business.qld.gov.au/running-business/support-services/mapping-data-imagery/queensland-globe/land-valuations
- **估值数据**: 包含 Property ID、real property description、current/new valuation、valuation date
- **更新频率**: 年度更新
- **付费查询**: Titles Queensland 提供按次付费查询 ($24.69/次 title search)
  - https://www.titlesqld.com.au/title-searches

#### 地籍/地块数据
- **免费**: ✅ **完全免费, CC-BY 许可**
- **数据产品**:
  1. **Property boundaries Queensland** (精简版) — 最小属性的地块边界
  2. **Cadastral data – Queensland – by area of interest** — 可按 LGA/city/suburb 提取
  3. **Queensland Spatial Cadastral Fabric (QSCF)** — 全州预打包 GDB 格式 (GDA2020 或 GDA94)
- **格式**: Shapefile, File Geodatabase (GDB)
- **URL**: https://www.business.qld.gov.au/running-business/support-services/mapping-data-imagery/data/digital-cadastral/access
- **WMS**: 提供 Web Map Service 供 GIS 直连
- **更新频率**: 持续维护

#### API
- **WMS (Web Map Service)**: 可直接在 GIS 应用中连接
- **QSpatial**: 在线下载门户
- **data.qld.gov.au CKAN API**: 数据集搜索和下载
- **限制**: 地籍数据开放程度高；销售数据完全不开放

#### 覆盖范围
- 全昆州

---

### 3. WA — Landgate

**主管机构**: Western Australian Land Information Authority (Landgate)
**门户**: https://www.landgate.wa.gov.au/
**开放数据门户**: Data WA — https://www.data.wa.gov.au/
**平台**: SLIP (Shared Location Information Platform)

#### 房产成交数据
- **免费数据**: ❌ **付费**
- **数据内容**: 1988年至今的 freehold/leasehold 成交记录
  - 成交价、日期、parcel details、卧室/浴室数等建筑属性
  - 分为 Residential 和 Commercial 两部分
- **格式**: .dat (历史批量), .xlsx + .dat + .pdf (增量更新)
- **获取方式**:
  1. 一次性数据提取 (需联系 CustomerExperience@Landgate.wa.gov.au)
  2. 定期订阅 (每周/每两周增量更新)
  3. VAR (Value Added Reseller) 协议
- **覆盖**: 全州 / Perth Metro+Mandurah / Perth Metro
- **单次报告**: Property Sales Reports — $7.40/份 (single) 或 $206.80/local authority
  - https://www.landgate.wa.gov.au/land-and-property/property-ownership/property-sales-and-trends/property-sales-reports

#### 地籍/地块数据
- **免费**: ⚠️ **需 SLIP 账户，可能收费**
- **数据产品**: Cadastre (Polygons) — 来自 Spatial Cadastral Database (SCDB)
- **覆盖**: 全 WA + Christmas Island + Cocos Keeling Islands
- **URL**: https://www.wa.gov.au/service/natural-resources/land-use-management/access-the-cadastre-polygons-dataset
- **注意**: "Access to this resource requires a SLIP account, and may involve a charge"
- **VAR 产品**: Cadastral data 可通过 Value Added Reseller 协议获取

#### API
- **SLIP**: WA 的空间数据基础设施平台
- **Data WA CKAN**: 数据发现
- **限制**: 销售数据严格商业化；地籍数据需账户

#### 特殊背景
- 2019年 WA 政府将 Landgate 的自动化产权服务部分私有化（$14.1亿出售给 Land Services WA），数据商业化程度高

---

### 4. SA — Land Services SA / SA Planning Portal

**主管机构**: Land Services SA (私有化运营) / Registrar-General / Valuer-General
**门户**: https://data.sa.gov.au/
**规划门户**: https://plan.sa.gov.au/ / https://www.saplanningportal.sa.gov.au/
**地图查看**: SA Property & Planning Atlas (SAPPA)

#### 房产成交数据
- **免费数据**: ⚠️ **仅有大阿德莱德地区中位数统计**
- **数据集**: Metro median house sales — 季度各suburb中位房价
  - https://data.sa.gov.au/data/dataset/metro-median-house-sales
- **格式**: XLSX, CSV, XLS
- **覆盖**: 仅 Metropolitan Adelaide（不含乡村地区）
- **更新频率**: 季度
- **逐笔成交**: 需通过 Property Edge (Land Services SA 的付费产品) 购买
  - https://propertyedge.app/ — 1993年以来 150万+ 条成交记录
  - 基于 SAILIS (South Australian Integrated Land Information System)

#### 地籍/地块数据
- **免费**: ❌ **付费，最低 $250 ex GST**
- **说明**: "South Australia cadastral data is not classified as open data"
- **来源**: Land Services SA
  - https://www.landservices.com.au/products-and-services/south-australian-cadastral-data
- **data.sa.gov.au 上有部分**: Land Parcels in City of Port Adelaide Enfield 等个别 council 的数据
  - 格式: Mixed (SHP, KML, GeoJSON)
  - 但不是全州覆盖
- **开放数据层**: SA Government 在 data.sa.gov.au 提供了一些规划相关图层:
  - Land Use Generalised (SHP, KML, GeoJSON)
  - Residential Broadhectare Land
  - Greater Adelaide Planning Region

#### API
- **data.sa.gov.au CKAN API** — 可搜索和下载开放数据集
- **SAPPA**: 在线查看工具，无批量 API
- **限制**: 地籍数据最封闭的州之一

---

### 5. TAS — The LIST (Land Information System Tasmania)

**主管机构**: NRE Tasmania (Department of Natural Resources and Environment Tasmania)
**门户**: https://www.thelist.tas.gov.au/
**数据门户**: LISTdata — https://listdata.thelist.tas.gov.au/opendata
**地图**: LISTmap — https://maps.thelist.tas.gov.au/
**服务**: LISTservices — https://services.thelist.tas.gov.au/

#### 房产成交数据
- **免费数据**: ❌ **付费**
- **产品**:
  1. **Premium Property Report** — $31.20/份
     - 包含: 房产信息、政府估值(1982年起)、历史成交记录、销售趋势(10年suburb级)、位置图、销售统计
  2. **Property Information Report** — 付费
  3. **Property Sales Report** — 付费
- **免费替代**: LISTmap 上可查看部分估值信息
- **无逐笔成交批量下载**

#### 地籍/地块数据
- **免费**: ✅ **LISTdata 开放数据免费下载**
- **数据产品**: LIST Cadastral Parcels
  - 全州 cadastral framework 的 polygon 空间索引
  - 属性: PID (Property Identifier), Volume and Folio
  - 数据来源: 1:5,000 orthophoto/cadastral map series
  - 2005年后的 subdivision 已拟合到绝对位置
- **格式**: ESRI Shapefile, ESRI Geodatabase, MapInfo TAB
- **更新频率**: 每6个月刷新开放数据下载
- **URL**: https://listdata.thelist.tas.gov.au/opendata

#### API
- **LISTservices**: 免费 REST-based Web Services
  - https://services.thelist.tas.gov.au/
  - 可集成到业务系统和应用中
  - 支持 REST 调用
- **限制**: 开放数据6个月更新一次；逐笔销售数据不免费

#### 覆盖范围
- 全塔州

---

### 6. NT — NT Land Information

**主管机构**: Department of Lands, Planning and Environment (原) / NT Land Information
**门户**: https://data.nt.gov.au/
**元数据**: NTLIS — http://www.ntlis.nt.gov.au/
**系统**: ILIS (Integrated Land Information System)

#### 房产成交数据
- **免费数据**: ❌ **无公开免费数据**
- **系统**: ILIS Valuation Data 包含估值信息
  - 覆盖: >95% NT parcels 有估值(最多3年内)
  - 但: 不公开批量下载
- **数据访问**: "Charges may apply for both hard and digital copy"
  - 需联系: Director Land Information
- **data.nt.gov.au**: 搜索无房产成交相关数据集

#### 地籍/地块数据
- **免费**: ❌ **需数据协议**
- **数据产品**: Digital Cadastral Database of the Northern Territory
  - 包含: parcel number, area, type, tenure reference, property name 等
  - 维护频率: continual (持续)
- **访问限制**: "Online access to digital data only available within the Northern Territory Government"
  - 外部用户需签 digital data agreement
  - "Charges may apply"
- **ANZLIC ID**: ANZNT0001000036
- **URL**: https://www.ntlis.nt.gov.au/metadata/export_data?metadata_id=2DBCB7711FB906B6E040CD9B0F274EFE&type=html

#### API
- **无公开 API**
- **ILIS Maps**: 在线查看工具，无批量接口
- **data.nt.gov.au**: 1072个数据集，无房产/地籍相关

#### 覆盖范围
- 全 NT（但数据获取极其困难）

---

### 7. ACT — ACT Planning / EPSDD

**主管机构**: Environment, Planning and Sustainable Development Directorate (EPSDD)
**门户**: https://www.data.act.gov.au/
**地理空间门户**: ACTmapi — https://actmapi-actgov.opendata.arcgis.com/
**规划门户**: https://www.planning.act.gov.au/

#### 房产成交数据
- **免费数据**: ⚠️ **仅有统计报告**
- **产品**: ACT Land and Property Report (半年报)
  - 包含: median price, price per m², median area, number of blocks/transactions
  - 按区域(district)和价格区间分类
  - 数据来源: Access Canberra settlements data
  - URL: https://www.planning.act.gov.au/__data/assets/pdf_file/0008/2998268/act-land-and-property-report-june-2025.pdf
- **格式**: PDF (统计报告，无逐笔数据CSV)
- **更新频率**: 半年
- **覆盖**: 全 ACT
- **无逐笔成交数据公开下载**

#### 地籍/地块数据
- **免费**: ✅ **ACTmapi 免费下载**
- **数据产品**: ACT Government Block (Current)
  - 包含: 地块位置和范围, sub category (PROPOSED, APPROVED, REGISTERED)
  - 不含 stratum blocks
  - 由 ACT Government Spatial Data Team 维护
- **格式**: CSV, KML, GeoJSON, GeoTIFF, SHP (通过 ArcGIS Open Data)
- **URL**: https://actmapi-actgov.opendata.arcgis.com/
- **许可**: Creative Commons Attribution 4.0 (CCBY 4.0)
- **系统**: Spatial Data Management System (SDMS)
  - https://www.planning.act.gov.au/professionals/survey-spatial/spatial-information/spatial-data-and-systems

#### API
- **ArcGIS REST Services**: 通过 ACTmapi Open Data (ArcGIS Hub)
  - 支持 GeoServices, WMS
- **data.act.gov.au CKAN API**: 数据集搜索
- **限制**: 地籍数据开放良好；销售数据仅有统计级

#### 覆盖范围
- 全 ACT

---

## 汇总评估

### 数据开放程度排名

| 排名 | 州 | 地籍数据 | 成交数据 | 总评 |
|:---:|------|------|------|------|
| 1 | **NSW** | ✅ 全免费+API | ✅ 全免费CSV | ⭐⭐⭐⭐⭐ 最开放 |
| 2 | **QLD** | ✅ CC-BY全免费 | ❌ 完全封闭 | ⭐⭐⭐⭐ 地籍好 |
| 3 | **TAS** | ✅ 免费下载 | ❌ 付费 | ⭐⭐⭐ 地籍好 |
| 4 | **ACT** | ✅ CCBY免费 | ⚠️ 仅统计 | ⭐⭐⭐ 小地区好 |
| 5 | **VIC** | ⚠️ 付费Vicmap | ⚠️ 仅中位数 | ⭐⭐ 半开放 |
| 6 | **SA** | ❌ $250+ 起步 | ⚠️ 仅部分中位数 | ⭐⭐ 较封闭 |
| 7 | **WA** | ⚠️ SLIP账户付费 | ❌ 商业化 | ⭐⭐ 商业化重 |
| 8 | **NT** | ❌ 需数据协议 | ❌ 无公开 | ⭐ 最封闭 |

### 建议

1. **地籍数据**: NSW、QLD、TAS、ACT 可直接获取；VIC 和 WA 需付费但数据质量高
2. **成交数据**: 仅 NSW 提供免费逐笔 CSV；VIC/SA/ACT 有中位数统计；其余州需商业购买
3. **全国覆盖方案**: 考虑 Geoscape Australia 的 National Cadastre 产品（商业方案，整合全澳）
4. **成交数据全国方案**: CoreLogic / PropTrack / Domain API 等商业数据商是唯一的全澳逐笔数据来源

---

*报告结束*
