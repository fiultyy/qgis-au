# 澳洲房产商业平台数据源逆向调研

> **调研日期**: 2026-07-24
> **目标**: 深挖 Domain / REA / PropTrack / CoreLogic / PriceFinder / Allhomes 等商业平台背后的**公开数据源**, 找到免费或低成本的获取方式。

---

## 一、政府房产成交数据（免费 / 低成本）

### 1.1 NSW — NSW Valuer General Property Sales Information (PSI)

| 项目 | 详情 |
|------|------|
| **来源** | NSW Valuer General / Value NSW, 数据来自 Land Registry Services 的 Notice of Sale |
| **费用** | **免费** (非商业用途, CC BY-NC-ND 4.0); 商业用途需授权 |
| **格式** | .DAT 文件 (按 LGA 分), 压缩为 ZIP; 社区项目提供清洗后的 CSV |
| **覆盖范围** | 全 NSW, 自 **1990 年至今** |
| **更新频率** | **每周**更新 |
| **数据字段** | 属性 ID, 地址, property type, 合同日期, settle date, purchase price, zonning 等 (不含业主姓名) |
| **获取方式** | 1. Valuation Services Portal 批量下载 (需注册) |
| | 2. [nswpropertysalesdata.com](https://nswpropertysalesdata.com) — 免费清洗后 CSV (近 6 年) |
| | 3. [GitHub: nsw-property-sales-data-cleaner](https://github.com/jameselks/nsw-property-sales-data-cleaner) — Python 下载+清洗脚本 |
| | 4. Land Values & Property Sales Map — 交互式地图, 单条/街道/suburb 查询 |
| **API** | NSW LRS 在线门户有 Free Search (地址/Title Reference/Lot&DP); 无正式 REST API, 但 data.nsw.gov.au 有 CKAN API 元数据 |
| **批量数据 URL** | [data.nsw.gov.au → Valuation Services Portal](https://data.nsw.gov.au/data/dataset?tags=Property) |
| **单条查询 URL** | [nsw.gov.au property sales search](https://www.nsw.gov.au/housing-and-construction/land-values-nsw/how-to-find-property-sales-information) |
| **Land Values Bulk** | 免费批量土地估值数据 (2017年7月起, 按 LGA, 月度 ZIP 更新) |
| **备注** | ⭐ **最佳免费数据源**。非商业 CC 许可, 研究用途完全够用。商业平台 (CoreLogic 等) 的底层数据之一 |

### 1.2 VIC — Valuer-General Victoria (VGV) Property Sales Data

| 项目 | 详情 |
|------|------|
| **来源** | Valuer-General Victoria, 数据来自 SRO settlement 申报 |
| **费用** | **分層:** |
| | • **公开汇总数据**: 免费 (CC BY 4.0) — 季度/年度 suburb 中位数 XLSX |
| | • **Property Sales Data (PSD)**: 仅限专业用户 (估价师, 房产中介, 政府, 律师), 需申请审核 |
| | • **单条 Sales History Report**: 通过 LANDATA 在线购买 (~几 AUD/条) |
| **格式** | XLSX (公开数据); 系统接口 (PSD 用户) |
| **覆盖范围** | 全 VIC 79 个 municipality |
| **更新频率** | 年度报告 (7月发布) + 季度报告 (3/6/9/12月) |
| **公开数据内容** | 年度: House/Unit/Land 按 suburb 的 10 年中位数; 季度: 15 个月中位数 + 季度变化% |
| **PSD 内容** | 完整成交记录 (地址, 价格, 日期, 物业类型等) — 类似 NSW PSI 但需资质审批 |
| **关键 URL** | |
| | • [land.vic.gov.au/property-sales-statistics](https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics) — 免费汇总数据 |
| | • [discover.data.vic.gov.au](https://discover.data.vic.gov.au/dataset?q=property+sales) — 13+ 个开放数据集 (CC BY 4.0) |
| | • [LANDATA PSD](https://www.landata.online/victorian-property-sales-data) — 专业用户完整数据 |
| | • [LANDATA Sales History](https://www.landata.online/property-sales-history-and-valuation-reports) — 单条购买 |
| **备注** | 公开数据只有 suburb 级中位数, **没有逐条交易记录**。逐条需 PSD 资质或 LANDATA 单条购买 |

### 1.3 QLD — Queensland Valuation and Sales (QVAS)

| 项目 | 详情 |
|------|------|
| **来源** | QLD Department of Resources / Valuer-General, QVAS 数据库 |
| **费用** | **分層:** |
| | • **土地估值数据**: 免费 (Queensland Globe 开放数据) |
| | • **单条成交查询**: 付费 (~$25/property, 通过 business centre 或参与 broker) |
| | • **批量成交数据**: 仅通过**持牌 Information Brokers** 购买 (QVAS Code of Conduct) |
| **格式** | 估值: 在线地图 (QLD Globe); 成交: 文本报告 / broker 产品 |
| **覆盖范围** | 全 QLD rateable properties |
| **更新频率** | 估值: 年度 (按 LGA 轮换); 成交: 实时录入 |
| **关键 URL** | |
| | • [qld.gov.au property sales products](https://www.qld.gov.au/environment/land/title/valuation/about/property-sales) — 官方产品及价格 |
| | • [QLD Globe Land Valuations](https://www.business.qld.gov.au/running-business/support-services/mapping-data-imagery/queensland-globe/land-valuations) — 免费估值地图 |
| | • [propertydatacodeofconduct.com.au](https://www.propertydatacodeofconduct.com.au) — QVAS Code & broker 列表 |
| **QVAS Broker** | RP Data (CoreLogic), PriceFinder, CMA, APM 等 — 价格数千到数万 AUD/年 |
| **备注** | QLD 是**成交数据最封闭的州**之一。无免费逐条成交数据, 数据请求平台有人公开抱怨过。底层估值数据免费 |

### 1.4 WA — Landgate Property Sales Reports

| 项目 | 详情 |
|------|------|
| **来源** | Landgate (WA Land Information Authority) — 2019年起部分商业化给 Land Services WA 财团 (Macquarie/Hesta/Sun Super, 40年 $14亿合约) |
| **费用** | **付费**, 按报告类型定价: |
| | • Single Property Sales Report — 付费 (约 $10-30) |
| | • Suburb/Area Sales Report — 付费 (按范围定价) |
| | • Weekly Sales 报告 — 免费公开 PDF (Strata WA 发布历史存档) |
| | • Sales Evidence Data — 付费 (通过 Landgate 数据服务) |
| **格式** | PDF + Excel + .DAT 文件 |
| **覆盖范围** | 全 WA (含 Christmas Island, Cocos Islands), 自 **1988 年至今** |
| **更新频率** | 每周 (Weekly Sales Reports) |
| **数据内容** | Sale date (通常为签合同日), 注册日期, transfer type (T/TF), property details |
| **关键 URL** | |
| | • [landgate.wa.gov.au/property-sales-reports](https://www.landgate.wa.gov.au/land-and-property/property-ownership/property-sales-and-trends/property-sales-reports) |
| | • [Weekly Sales Archive](https://www.strata.wa.gov.au/siteassets/documents/land-and-property/property-ownership/property-sales-and-trends/top-weekly-sales/) — 历史周报免费 PDF |
| | • [Map Viewer Plus](https://www.landgate.wa.gov.au/location-data-and-services/maps/online-maps/map-viewer-plus) — 交互式查询购买 |
| | • [Sales Evidence Data](https://www.landgate.wa.gov.au/location-data-and-services/discovering-landgate-data/sales-evidence-data) |
| **备注** | WA 已将 title 和 transaction processing 商业化运营, 费用中等。估值数据 (GRV/UV) 可免费查询 |

### 1.5 SA — Land Services SA / SAILIS

| 项目 | 详情 |
|------|------|
| **来源** | Land Services SA (2017年商业化, 私营运营), Office of the Valuer-General (OVG) 监管 |
| **费用** | **付费**, 但有多种产品: |
| | • Property Research Report (含估值+成交) — 通过 SAILIS 购买 |
| | • Register Search (Title) — 付费 |
| | • 历史搜索 (1858-1992) — **免费** (SAILIS historical search) |
| **格式** | 在线报告 / PDF |
| **覆盖范围** | 全 SA |
| **更新频率** | 实时 (title registration) |
| **关键产品** | |
| | • Property Edge (Land Services SA 的产品) — 150 万+ 成交记录 (1993起), 含 stamped value |
| | • SAILIS — Title/plan/dealing 搜索 |
| **关键 URL** | |
| | • [sailis.lssa.com.au](https://sailis.lssa.com.au) — SAILIS 门户 |
| | • [landservices.com.au](https://www.landservices.com.au) — 产品和报告 |
| | • [Property Edge](https://propertyedge.app) — 成交数据库 (含 stamped value) |
| | • [State Library SA SAILIS Guide](https://guides.slsa.sa.gov.au/SAILIS) — 免费使用指南 |
| **备注** | SA 的成交数据 (1993起) 通过 Property Edge 覆盖较好。历史 title (1858-1992) 完全免费 |

### 1.6 其他州/领地

| 州/领地 | 数据源 | 费用 | 备注 |
|---------|--------|------|------|
| **TAS** | LIST (Land Information System Tasmania) / OVG | 估值免费, 成交付费 | listdata.thelist.tas.gov.au |
| **NT** | NT Land Information | 付费 | NTLIS 数据有限公开 |
| **ACT** | ACT Revenue Office / Access Canberra | 部分免费 | DA 数据可查 |

---

## 二、AUSTRAC 反洗钱 / 房产交易

| 项目 | 详情 |
|------|------|
| **机构** | AUSTRAC (Australian Transaction Reports and Analysis Centre) |
| **数据类型** | Suspicious Matter Reports (SMRs), Threshold Transaction Reports (TTRs >$10k), International Funds Transfer Instructions (IFTIs) |
| **房产关联** | AUSTRAC 估计 2020 年仅与中国关联的犯罪资金就通过澳洲房产洗了 **$10 亿**; 2019-2024 AFP 没收超过 $7.2 亿房产 |
| **公开数据?** | ❌ **不公开**。AUSTRAC 数据仅向监管机构、执法部门和签约伙伴提供 |
| **公开报告** | AUSTRAC 发布行业简报、typologies 报告, 包含去标识化的案例分析 |
| **Tranche 2 改革** | 2026年7月1日起, 房产中介/开发商/买家代理正式纳入 AML/CTF 制度 (注册截止 2026年3月31日) |
| **对数据获取的影响** | 未来房产交易将有更多 KYC 记录, 但仍非公开数据 |
| **关键 URL** | [austrac.gov.au](https://www.austrac.gov.au) — 报告和简报 |
| **备注** | AUSTRAC 数据**不可作为商业房产数据源**。但其公开的 typologies 报告对理解洗钱热点区域有参考价值 |

---

## 三、ABS (Australian Bureau of Statistics)

### 3.1 Census 人口普查数据

| 项目 | 详情 |
|------|------|
| **数据源** | ABS Census of Population and Housing (5年一次, 最新 2021, 下次 2026) |
| **费用** | **全部免费** |
| **地理粒度** | **SA1** (约 400 人, 最小单元), SA2, LGA, Postal Area, Mesh Block |
| **房产相关数据** | |
| | • Dwelling type (house/unit/apartment) |
| | • Tenure type (owned outright/with mortgage/rented) |
| | • Rent payments / mortgage repayments |
| | • Dwelling structure (separate house/semi/townhouse/flat) |
| | • Occupancy status (occupied/unoccupied on Census night) — **空置率!** |
| | • Household composition, persons per dwelling |
| | • Income (个人/household, 按 SA2 可查) |
| **工具** | |
| | • **TableBuilder** — 免费在线建表, 可导出 CSV/Excel/SDMX, 支持自定义 SA1/SA2 |
| | • **MicrodataDownload** — 5% 样本 microdata (SAS/STATA/SPSS) 免费下载 |
| | • **DataLab** — 详细 microdata (需审批, ABS 办公室内使用) |
| | • **Data by Region** (dbr.abs.gov.au) — 区域统计对比工具 |
| | • ** MADIP** — 整合 Census + 税务 + 健康等多源数据 (需审批) |
| **关键 URL** | |
| | • [abs.gov.au Census TableBuilder](https://www.abs.gov.au/statistics/microdata-tablebuilder/available-microdata-tablebuilder/census-population-and-housing) |
| | • [abs.gov.au Housing Census](https://www.abs.gov.au/statistics/people/housing/housing-census/latest-release) |
| | • [abs.gov.au Housing Occupancy & Costs](https://www.abs.gov.au/statistics/people/housing/housing-occupancy-and-costs/latest-release) |
| | • [abs.gov.au Household Income & Wealth](https://www.abs.gov.au/statistics/economy/finance/household-income-and-wealth-australia/latest-release) — 含 **Gini coefficient** |

### 3.2 非 Census 房产数据

| 数据 | 频率 | 粒度 | URL |
|------|------|------|-----|
| Estimated Dwelling Stock | 季度 | National/State/SA2 | abs.gov.au → Residential Property |
| Building Approvals | 月度 | LGA/SA2 | abs.gov.au/statistics/industry/building-and-construction |
| Residential Property Price Index | 季度 | Capital city | abs.gov.au/statistics/economy/price-indexes-and-inflation/residential-property-price-indexes |
| Housing Finance / Lending Indicators | 月度 | National/State | abs.gov.au → Lending indicators |

### 3.3 Gini 系数 & 收入分布

| 项目 | 详情 |
|------|------|
| **来源** | ABS Survey of Income and Housing (SIH), 2年一次 |
| **最新** | 2019-20 (下一轮 2023-24 发布中) |
| **粒度** | National / State / SA2 (Census 可到 SA1) |
| **内容** | Gini coefficient (equivalised disposable household income), income quintiles, wealth distribution |
| **费用** | 免费 |
| **URL** | [abs.gov.au Household Income & Wealth](https://www.abs.gov.au/statistics/economy/finance/household-income-and-wealth-australia/latest-release) |

---

## 四、各州政府开放数据门户

### 4.1 开放数据门户汇总

| 门户 | URL | 房产相关数据 | API |
|------|-----|-------------|-----|
| **data.nsw.gov.au** | [data.nsw.gov.au](https://data.nsw.gov.au) | Property Sales (PSI), Land Values, Cadastre, DA, 地址 | CKAN API |
| **discover.data.vic.gov.au** | [discover.data.vic.gov.au](https://discover.data.vic.gov.au) | Property Sales Report (13+ datasets), Vicmap Property parcels, 建筑许可 | CKAN API |
| **data.qld.gov.au** | [data.qld.gov.au](https://www.data.qld.gov.au) | QLD Globe (估值), cadastre; **成交数据不在开放数据** | CKAN API |
| **data.wa.gov.au** | [data.wa.gov.au](https://data.wa.gov.au) | SLIP portal (Landgate data), cadastre, 地名 | CKAN API |
| **data.sa.gov.au** | [data.sa.gov.au](https://data.sa.gov.au) | 有限房产数据 (大部分 NSW 的交叉数据) | CKAN API |
| **data.gov.au** | [data.gov.au](https://data.gov.au) | 国家级聚合, 30,000+ datasets, 含各州 cross-ref | CKAN API (MAGDA) |
| **ACT Open Data** | [data.act.gov.au](https://www.data.act.gov.au) | DA tracker, property sales | Socrata API |

### 4.2 关键开放数据集

| 数据集 | 州 | 格式 | 费用 | URL |
|--------|-----|------|------|-----|
| NSW Property Sales Information (PSI) | NSW | .DAT/ZIP | 免费 (非商业) | Valuation Services Portal via data.nsw |
| NSW Cadastre (DCDB) | NSW | WMS/WFS/REST | 免费 | [data.nsw → NSW Cadastre](https://data.nsw.gov.au/data/dataset/spatial-services-nsw-cadastre) |
| NSW Bulk Land Values | NSW | .DAT/ZIP | 免费 | data.nsw → Valuation Services Portal |
| VIC Property Sales Report (median) | VIC | XLSX | 免费 (CC BY 4.0) | discover.data.vic.gov.au |
| VIC House Prices by Small Area | VIC | XLSX | 免费 | discover.data.vic.gov.au |
| Vicmap Property Parcel Table | VIC | spatial layer | 免费 (CC BY 4.0) | discover.data.vic.gov.au |
| QLD Globe Land Valuations | QLD | 在线地图 | 免费 | Queensland Globe |
| WA Sales Evidence Data | WA | .dat/PDF | 付费 | Landgate |
| Digital Atlas of Australia | National | 在线地图/API | 免费 | atlas.australia.gov.au |

---

## 五、Title Search 费用与渠道

### 5.1 各州 Title Search 费用 (2025-26 财年)

| 州 | 运营机构 | 单次 Title Search 费用 | 批量折扣 | 在线门户 |
|----|---------|----------------------|---------|---------|
| **NSW** | NSW Land Registry Services (NSW LRS) | **$18.00** (含 GST, 含 $5.14 Torrens Assurance Fund levy) | 信息 brokers 有批量价 | [online.nswlrs.com.au](https://online.nswlrs.com.au) |
| **VIC** | SERV (Land Registry) / LANDATA | ~$7-15 (Register Search Statement) + Land Index Search Fee (~$8 若需通过地址查找 volume/folio) | 通过 broker 可批量 | [landata.vic.gov.au](https://www.landata.vic.gov.au) / [landata.online](https://www.landata.online) |
| **QLD** | Dept of Resources / Title Queensland | ~$15-25 per search | 通过 broker | [business.qld.gov.au](https://www.business.qld.gov.au) |
| **WA** | Landgate / Land Services WA | ~$12-20 per title | MyLandgate Account 有订阅 | [landgate.wa.gov.au](https://www.landgate.wa.gov.au) |
| **SA** | Land Services SA / SAILIS | ~$10-20 (Register Search Plus) | SAILIS 账户 | [sailis.lssa.com.au](https://sailis.lssa.com.au) |
| **TAS** | LIST | ~$10-15 | — | thelist.tas.gov.au |
| **ACT** | Access Canberra | ~$15-20 | — | act.gov.au |

### 5.2 信息 Broker (批量折扣渠道)

| Broker | 覆盖 | 优势 | 价格模型 |
|--------|------|------|---------|
| **InfoTrackGO** | 全国 | 整合 title + planning + property reports | 按次, 预付套餐 |
| **Landchecker** | 全国 | Title + planning zones + overlays | Title ~$20.34/次 |
| **Fynd.info** | 全国 | 简单界面, title + deposited plan | ~$19.90/次起 |
| **RP Data (CoreLogic)** | 全国 | 最全面房产数据 + AVM | 订阅制 (~$200+/月) |
| **PropTrack** | 全国 | REA Group 旗下 | 订阅制 |
| **National Property Data** | 全国 | 成交 + 估值 | 订阅制 |
| **Tri Global** | 主要 QLD/NSW | QVAS 授权 broker | 订阅制 |

### 5.3 免费 Title 搜索

| 渠道 | 说明 |
|------|------|
| NSW LRS Free Search | 基础信息 (title ref, lot/DP, 地址) 免费; 完整 title 需付费 |
| SAILIS Historical (SA) | 1858-1992 年历史 title **完全免费** (查看/下载) |
| NSW Historical Land Records Viewer (HLRV) | 历史地图/plan/title 免费查看 |

---

## 六、Council / Local Government DA (Development Application) 数据

### 6.1 NSW — Planning Portal DA API ⭐

| 项目 | 详情 |
|------|------|
| **数据源** | NSW Planning Portal (ePlanning) — 所有 council 强制使用 (2021年7月起) |
| **费用** | **免费** (CC BY 许可) |
| **格式** | REST API (JSON), 有 Data Dictionary |
| **覆盖范围** | 全 NSW councils (290+), 自 **2019年1月**起 (部分历史数据) |
| **更新频率** | **每日** |
| **数据内容** | DA number, address, category (Residential/Commercial/etc), estimated cost, lodged_date, status |
| **关键 URL** | |
| | • [data.nsw.gov.au → Online DA Data API](https://data.nsw.gov.au/data/dataset/online-da-data-api) |
| | • [NSW Planning Portal Open Data](https://www.planningportal.nsw.gov.au/opendata/dataset/online-da-data-api) |
| | • [NSW Application Tracker](https://www.planningportal.nsw.gov.au/map) — 在线搜索界面 |
| **备注** | ⭐ **最佳 DA 开放数据源**。有正式 REST API + Data Dictionary |

### 6.2 第三方 DA 数据聚合

| 服务 | 覆盖 | 费用 | 特点 |
|------|------|------|------|
| **Council DA** (council-da.com) | 全国 250+ councils | 搜索免费; PDF report $29.95; API from $49/月 | 统一 REST API, webhooks, 36年历史, 地理搜索 |
| **PlanningAlerts** (planningalerts.org.au) | 全国 (社区驱动) | 免费 | 开源, RSS/email alerts |

### 6.3 其他州 DA 数据

| 州 | 状态 | 备注 |
|----|------|------|
| **VIC** | 分散 | 各 council 独立发布, 部分 council 有 open data (如 City of Melbourne 193 个 datasets); 汇总可在 data.gov.au 搜索 |
| **QLD** | 分散 | 部分 council 有 DA tracker; PD Online (Brisbane 等) |
| **WA** | 分散 | WALGA 报告 DA 统计; 各 council 独立 portal; WA 2023年改革后 single house DA 多由决策方处理 |
| **SA** | 分散 | PlanSA portal 有在线 DA 搜索 |
| **ACT** | 较好 | data.act.gov.au 有 DA tracker (Socrata API) |

---

## 七、总结: 数据源优先级矩阵

### 免费高价值数据源 ⭐⭐⭐

| 数据源 | 数据类型 | 覆盖 | 推荐 |
|--------|---------|------|------|
| **NSW PSI (Valuer General)** | 逐条成交记录 (1990起) | NSW | ⭐ 最佳免费成交数据, 已有 CSV |
| **NSW Planning Portal DA API** | DA 申请 (2019起) | NSW | ⭐ 最佳 DA API |
| **ABS Census TableBuilder** | 人口/住房/收入/空置率 (SA1级) | 全国 | ⭐ 最全面人口/住房数据 |
| **VIC Property Sales Reports** | suburb 中位数 | VIC | 中位数级别, 非逐条 |
| **data.gov.au / 各州门户** | 多种开放数据 | 全国 | 元数据搜索入口 |

### 低成本数据源 ⭐⭐

| 数据源 | 数据类型 | 费用 | 备注 |
|--------|---------|------|------|
| **LANDATA (VIC)** | 单条 Sales History | ~$7-15/条 | 按需购买 |
| **NSW LRS Title Search** | Title 证书 | $18/条 | 含所有权信息 |
| **Landgate (WA)** | Property Sales Report | ~$10-30/条 | 按需购买 |
| **SAILIS (SA)** | Property Research Report | ~$10-20/条 | 按需购买 |
| **Council DA API** | 全国 DA 数据 | $49+/月 | 统一 API |
| **Property Edge (SA)** | 成交数据库 | 订阅 | 含 stamped value |

### 高成本 / 封闭数据源 ⭐

| 数据源 | 费用 | 备注 |
|--------|------|------|
| **CoreLogic RP Data** | ~$200+/月, 企业级可达数千/月 | 最全面商业房产数据 |
| **PropTrack** | 订阅制 | REA Group 旗下 |
| **QVAS bulk data** | 通过 broker, 数千-$20k+ | QLD 成交数据, 无直接公开渠道 |
| **AUSTRAC** | 不公开 | 仅执法/监管用途 |

---

## 八、对商业平台数据链的逆向推断

```
Domain / REA / PropTrack / CoreLogic
    ↑ 数据整合层
    │
    ├── 成交数据 ──── 各州 Valuer General (NSW PSI, VIC PSD, QVAS, Landgate, SAILIS)
    │                 ↑ 这些 VG 数据本身来自 Notice of Sale / settlement 申报
    │
    ├── 估值/AVM ──── 自己的算法模型 + VG 土地估值 + hedonic regression
    │                 输入: 成交数据 + 属性特征 + 地理因素
    │
    ├── 属性特征 ──── Title records (各州 Land Registry) + Council DA + 实地/crowdsource
    │
    ├── 市场指标 ──── ABS (Census, building approvals, RPPI) + 自己聚合
    │
    ├── 租金数据 ──── 自己的平台 listing + REIV/REIQ 等行业协会
    │
    ┕── 区域分析 ──── ABS Census (SA1/SA2) + SEIFA + 自有成交聚合
```

**核心发现**: 商业平台的**原始数据 80%+ 来自政府公开/低成本来源**, 其增值主要在:
1. **数据清洗与标准化** — 统一全国格式, 修正异常值
2. **属性特征丰富** — 合并 title + DA + 估值 + 地理数据
3. **AVM 模型** — hedonic pricing model, 这是真正的技术壁垒
4. **实时性** — 有些平台通过 settlement agent/council 直接获取 pre-settlement 数据

---

*调研完成。如需深入某个具体数据源的获取实现, 请指明方向。*
