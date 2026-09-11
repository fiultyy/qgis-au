# 房产换手节点数据反推策略调研报告

> **目标**: 在封闭成交数据（CoreLogic/Domain/REA 付费墙）不可批量获取的前提下，利用房产换手的公开痕迹节点反推成交信息。
> ** focus**: NSW（特别是大 Sydney 区域），部分全国性来源。
> **日期**: 2026-07-24

---

## 可行性排序总览

| 排名 | 数据源 | 反推准确度 | 获取难度 | 成本 | 优先级 |
|------|--------|-----------|---------|------|--------|
| 1 | NSW Valuer General Property Sales Data | ★★★★★ | 低 | 免费 | **P0** |
| 2 | Domain/REA 拍卖结果（周末公开页） | ★★★★☆ | 中 | 免费 | **P0** |
| 3 | Domain Developer API | ★★★★☆ | 中 | 付费（需审批） | **P1** |
| 4 | Council DA 数据（NSW Planning Portal Open API） | ★★★☆☆ | 低 | 免费 | **P1** |
| 5 | Title Search / Transfer Dealing（NSW LRS） | ★★★★★ | 高 | 付费 per search | **P1** |
| 6 | Domain/REA 已售 listing + 价格历史 | ★★★☆☆ | 中 | 免费/付费 | **P2** |
| 7 | Old Listings 历史广告价 | ★★☆☆☆ | 低 | 免费 | **P2** |
| 8 | PEXA Property Insights 报告 | ★★☆☆☆ | 低 | 免费（宏观） | **P2** |
| 9 | NSW LRS 免费在线查询 | ★★★☆☆ | 高 | 免费 | **P2** |
| 10 | 水电燃气/NBN 换户 | ★☆☆☆☆ | 极高 | N/A | **P3** |
| 11 | Council Rates / 10.7 Certificate | ★☆☆☆☆ | 极高 | 付费 | **P3** |
| 12 | Stamp Duty / OSR | ★☆☆☆☆ | 极高 | N/A | **P3** |

---

## 1. NSW Valuer General Property Sales Data ⭐⭐⭐⭐⭐

**——最核心、最可靠、且免费的数据源**

### 数据内容和质量
- **官方成交数据**：包含实际成交价（sale price）、成交日期、物业地址、title reference、property ID、lot/plan 号、property type、land area 等
- 覆盖 1990 年至今的所有 NSW 成交记录
- 数据来源为法定过户时上报给 VG 的信息，**准确度极高**
- 按 LGA（Local Government Area）分文件

### 获取方式：免费批量下载
- **官方入口**: `https://valuation.property.nsw.gov.au/embed/propertySalesInformation`
  - 提供 CSV 格式的批量下载（delimited file format）
  - 按时间段分文件，每日更新
  - 需注册 Valuation Services Portal 账号
  - 采用 Creative Commons Attribution 4.0 许可（开放数据）
- **第三方便捷入口**: `https://nswpropertysalesdata.com`
  - 开发者已将 VG 原始数据清洗为易用 CSV（ZIP 包）
  - 包含最近 6 年数据，每日凌晨 5 点更新
  - 一键下载，GitHub 开源清洗代码
  - **最推荐起点**
- **UNSW City Futures**: `https://citydata.ada.unsw.edu.au/dataset/nsw-valuer-general-property-sales`
  - 学术机构整理版，含 1990 年至今完整数据
  - 已做地理空间关联（链接 cadastre parcel）
- **NSW Government 交互地图**: NSW Land Values and Property Sales Map
  - 在线可视化工具

### 覆盖范围
- **全 NSW**，含 Sydney 大都会区及偏远地区
- 时间跨度：1990 至今

### 反推成交信息准确度：★★★★★
- 数据本身就**是**成交数据（非反推），包含真实成交价
- VG 数据是 CoreLogic 等商业数据源的上游来源之一
- 少量延迟：成交后约 1-3 个月才出现在批量数据中（取决于上报和数据处理周期）

### 实施难度：极低
- 直接下载 CSV，导入数据库/QGIS 即可分析
- 第三方网站已做清洗，开箱即用

### 备注
- VG 还提供 **Bulk Land Value Data**（月度更新，免费 CSV），包含每块土地的估值信息，可辅助判断成交后价值变化趋势
- VG 的 **land value** 不等于成交价，但成交会触发重新估值，可以用来交叉验证

---

## 2. Domain/REA 周末拍卖结果 ⭐⭐⭐⭐

### 数据内容和质量
- 每周末拍卖结果：清盘率、成交价（或区间）、流拍、撤回数量
- 按 suburb 细分
- Domain: `/auction-results/sydney` — 含具体成交价
- REA: `/auction-results/nsw` — 含 suburb 级别统计

### 获取方式
- **公开网页免费查看**: 
  - Domain: `https://www.domain.com.au/auction-results/sydney`
  - REA: `https://www.realestate.com.au/auction-results/nsw`
- **Domain 已售 listing**: `https://www.domain.com.au/sold-listings/sydney-region-nsw`
  - 可按 suburb 筛选，含成交价（部分隐藏需注册）
- **抓取策略**: 
  - 每周一/二抓取周末结果（数据稳定在周初上线）
  - 模拟人类浏览，按 suburb 逐页查询
  - 可用 Apify 等平台的现成 scraper（如 `domain-com-au-scraper`）
  - 速率控制：每次请求间隔 5-10 秒，每日不超过 200-300 个 suburb

### 覆盖范围
- 主要城市（Sydney, Melbourne, Brisbane 等）
- 仅拍卖物业（约占 Sydney 成交的 30-50%，郊区更低）

### 反推准确度：★★★★☆
- 拍卖成交价是**真实成交价**
- 非拍卖物业（private treaty）不在拍卖结果中
- Domain 已售列表含 private treaty 但价格可能有延迟或缺失

### 实施难度：中等
- 公开页面结构稳定，可用 web_fetch 或浏览器自动化抓取
- 需注意反爬机制（频率限制、CAPTCHA）

---

## 3. Domain Developer API ⭐⭐⭐⭐

### 数据内容和质量
- **Sales Results API**: `GET /v1/salesResults/{city}/listings`
  - 返回最近报告期内的成交 listing 汇总
  - 含成交价（sale price）、结果代码（AUSD/PTSD 等）
  - 可查完整 listing 详情
- **Listings API**: 获取在售/已售/已租 listing 详细数据
- **Properties API**: 物业详情、估值、历史

### 获取方式：付费（需审批注册）
- **Domain Developer Portal**: `https://developer.domain.com.au`
- 注册账号（GitHub/Google/Email），创建项目获取 API Key
- **数据分级访问**: 不同 access level 能看到不同字段（价格等敏感字段需高级别）
- 免费试用期可用 Live API Browser 测试
- 正式商用需与 Domain 商务团队洽谈（费用未公开，预计数百至数千澳元/月）

### 覆盖范围
- 全国（Domain 覆盖的所有区域）

### 反推准确度：★★★★☆
- 拍卖成交价精确；private treaty 价格标记可能含 "warning"（PTSW = 可能不可靠）

### 实施难度：中等
- RESTful API，JSON 格式，标准 HTTP 调用
- 主要难点在获取高级 access level 的审批

---

## 4. Council DA 数据（NSW Planning Portal Open API）⭐⭐⭐

### 数据内容和质量
- **DA（Development Application）公开记录**：地址、申请类型、申请人、 lodgement 日期、决定状态、决定日期
- 新房建设、拆除、加建、装修等申请 = **可能的交易后行为信号**
- 部分含 cost estimate（工程造价估算，非成交价）
- **不直接含成交价**

### 获取方式：免费 API
- **NSW Planning Portal Open Data**: `https://www.planningportal.nsw.gov.au/opendata/dataset/online-da-data-api`
  - 提供 Open API（RESTful），每日更新
  - 含 2019 年 1 月以来所有通过 Planning Portal 提交的 DA
  - 数据字典（Data Dictionary）公开下载
  - Creative Commons 许可
  - 联系: `data.broker@environment.nsw.gov.au`
- **DA Radar**（第三方聚合）: `https://da-radar.com.au/nsw`
  - 聚合 384,678+ 条 NSW DA 记录，每夜更新
  - 按 council/suburb 浏览
  - 非官方但数据组织更友好
- **各 Council 自己的 DA Tracker**: 
  - City of Sydney: `https://www.cityofsydney.nsw.gov.au/development-applications/search-development-applications`
  - 其他 council 类似（搜索 `[council name] DA tracker`）

### 覆盖范围
- 全 NSW（2019 年起），部分 council 有更早的历史数据

### 反推准确度：★★★☆☆
- DA 不是换手的直接证据，但是**强间接信号**
- 逻辑链：新房建设/大规模装修 DA → 可能是新业主购入后翻建
- 时间窗口：DA lodgement 通常在成交后 3-12 个月
- 拆除 DA → 更强的换手信号（旧房推倒重建）
- 需结合 VG 数据交叉验证

### 实施难度：低（API）/ 中（分析建模）
- API 调用简单
- 难点在于从 DA 类型中推断"是否为换手后行为"，需要建立分类模型

---

## 5. Title Search / Transfer Dealing（NSW LRS）⭐⭐⭐⭐⭐（准确度最高但付费）

### 数据内容和质量
- **Title Search**: 当前业主姓名、产权信息、encumbrances
- **Transfer Dealing**: 成交日期、转移金额（部分情况）、transferor → transferee
- **这是最权威的产权转移记录**
- 每个 dealing 有唯一 dealing number

### 获取方式：付费 per search
- **NSW LRS Online Portal**: `https://online.nswlrs.com.au`
  - **免费查询**: title reference 查询（获取 street address）、property address 查询（获取 property number）、land value 查询（业主本人）、HLRV（历史地图/计划/产权）
  - **付费查询**: 完整 Title Search（~$19.90+/次）、dealing 搜索、historical title search
- **Information Brokers**（授权经销商）:
  - InfoTrack / InfoTrackGO: `https://infotrackgo.com.au/property/title-search`
  - Fynd: `https://www.fynd.info/products/title-search`（$19.90 起）
  - Symchart, PSI Global, Dye & Durham 等
  - 批量购买可能有折扣
- **无免费批量渠道** — 这是最大的限制

### 覆盖范围
- 全 NSW，所有 Torrens Title 产权（覆盖 >99% 住宅）

### 反推准确度：★★★★★
- 100% 准确 — 这是法定记录
- Transfer dealing 直接记录成交日期和参与方
- 但价格信息不一定完整（部分 transfer 不记录金额）

### 实施难度：高（成本驱动）
- 单次搜索成本 $15-30+
- 批量搜索 1000 个地址 = $15,000-30,000
- **策略**: 仅对高价值目标地址做定向 title search，不用于批量
- 可结合 VG 免费数据先定位，再用 title search 验证关键样本

### 免费部分
- NSW LRS 免费在线工具可做**地址 ↔ title reference 互查**，这是构建数据索引的基础
- HLRV（Historical Land Records Viewer）可免费查看数字化历史产权（1860s-1990s），对现代成交用处有限

---

## 6. Domain/REA 已售 Listing + 价格历史 ⭐⭐⭐

### 数据内容和质量
- 已售 listing 保留在 Domain/REA 上一段时间（通常 3-6 个月在首页可搜，更久的通过 property profile 查看）
- **Domain Property Profile**: `https://www.domain.com.au/property-profile`
  - 按地址搜索，显示估值、历史 listing、历史成交价（部分）
- **REA Sold**: `https://www.realestate.com.au/sold`
  - 已售列表，含成交价区间或具体价格

### 获取方式
- 单地址查询：免费，直接在网站搜索
- 批量：需 scraper 或 Domain API
- **Apify Domain Scraper**: 第三方现成爬虫工具
- **Quiet Listings** (`https://www.quietlistings.com.au`): 新兴平台，追踪价格变动和 campaign 历史

### 覆盖范围
- 全国，但历史数据深度有限（通常只保留近几年的在线 listing）

### 反推准确度：★★★☆☆
- 显示的价格可能是广告价（asking price）而非实际成交价
- 拍卖结果中显示的价格更准确
- Domain Property Profile 有时显示历史成交价，来源可能就是 VG 数据

### 实施难度：中等
- 单点查询容易，批量需 scraper + 反检测策略
- 不适合全量覆盖，适合定向地址核查

---

## 7. Old Listings 历史广告价 ⭐⭐

### 数据内容和质量
- **OldListings.com.au**: `https://www.oldlistings.com.au`
  - 澳洲最大的历史广告房价档案（自 2006 年起）
  - 超过 1500 万条记录
  - 显示**广告价**（asking price），非成交价
  - 免费，可按地址/suburb 搜索

### 获取方式：免费
- 网页搜索，可能有速率限制
- 未见公开 API

### 覆盖范围
- 全国，但覆盖深度因地区而异

### 反推准确度：★★☆☆☆
- 广告价 ≠ 成交价（可能高估或低估 5-15%）
- 但可以判断：广告下线时间 ≈ 大致成交时间
- 价格变动历史可以反映 market sentiment

### 实施难度：低
- 简单网页搜索，可做轻量级抓取

---

## 8. PEXA Property Insights 报告 ⭐⭐

### 数据内容和质量
- PEXA 是澳洲最大的电子房产过户平台（ASX 上市，PXA.AX）
- 自 2013 年以来处理超过 2000 万笔房产过户
- 发布季度/年度 **Property Insights Report**（免费 PDF）
- 含：settlement volumes、settlement values、州级/区域趋势
- FY25 数据：5 个州 722,000 套房产过户，总值 $726.6B

### 获取方式：免费
- `https://www.pexa-group.com/content-hub/property-insights-and-reports`
- 季度更新，直接下载 PDF

### 覆盖范围
- 全国级别（5 个大陆州），分州统计
- **无地址级别数据**

### 反推准确度：★★☆☆☆
- 仅宏观统计，无法反推个体成交
- 价值在于**市场趋势校准**：与 VG 数据配合，判断某段时间的成交量是否异常

### 实施难度：极低
- 直接下载报告即可

### PEXA 衍生数据
- PEXA 与 Domain 合作发布 "Property Journey Data" 报告（PDF 公开）
  - 分析 buyer demand 与 settlement 的相关性
  - 含 suburb 级别的 correlation 分析
  - 来源: `https://static.domain.com.au/content/marketing/Property_Journey_Data.pdf`

---

## 9. NSW LRS 免费在线查询 ⭐⭐⭐

### 数据内容和质量
- **Title Reference Enquiry**: title reference → street address（免费）
- **Property Address Enquiry**: address → property number/title reference（免费）
- **Land Value Search**: 业主可免费查自己的 land value
- **HLRV (Historical Land Records Viewer)**: 历史 map/plan/title（免费）
- **Document Inquiry**: 按 PA number 查 Old System deed（免费）

### 获取方式：免费，在线 Portal
- `https://online.nswlrs.com.au`

### 反推准确度：★★★☆☆
- 免费 query 不直接显示成交价和业主姓名
- 但可以做**地址 ↔ title 关联**，这是所有后续分析的基础索引
- HLRV 可查历史 chain of title（1860s-1990s），对老房产的历史成交有帮助

### 实施难度：高（非自动化）
- 在线表单查询，需逐个手动操作
- 无批量 API
- 适合构建小规模精确索引

---

## 10. 水电燃气/NBN 换户 ⭐（不推荐）

### 调研结论
- **Sydney Water**: 买卖房产时自动过户账户，**不公开**户主信息。"When you buy or sell any property, you don't need to connect or disconnect your services. We automatically transfer the account into the new owner's name."
- **电力公司**: 各家零售商（AGL, Origin, EnergyAustralia 等）客户数据完全保密，无公开渠道
- **NBN Co**: 新连接申请（new development）需付 ~$900 费用，但连接记录不公开。NBN rollout map 仅显示技术类型和可用性
- **无任何已知的聚合或泄露公开版本**

### 反推准确度：★☆☆☆☆（即使能获取）
- 新户主可能是租客而非业主
- 水电过户是自动的，不代表有独立的"换户信号"

### 实施难度：极高（基本不可行）
- 涉及隐私法（Privacy Act 1988）和 GIPA 法案限制
- 无合法批量获取渠道

### 结论：**放弃此路径**

---

## 11. Council Rates / Section 10.7 Certificate ⭐（不推荐批量）

### Section 10.7 Certificate（原 Section 149）
- **内容**: 物业 zoning、planning controls、constraints（洪水、灌木火、污染等）
- **用途**: 买卖合同必备附件，但不包含成交价或业主信息
- **费用**: 约 $130-300/份（各 council 不同）
- **通过 NSW Planning Portal 在线申请**: `https://www.planningportal.nsw.gov.au/development-and-assessment/post-consent-certificates/online-section-107-planning-certificate-service`

### Council Rates Notice
- Council 的 ratepayer 信息在业主变更时会更新
- **但**: ratepayer 个人信息受 Privacy Act 保护，不公开
- 可通过 GIPA（Government Information Public Access）申请特定信息，但：
  - 个人信息（姓名、地址）通常被拒绝
  - 20 个工作日处理周期
  - 申请费 $30-$130
  - 不保证能获得有用信息

### 反推准确度：★☆☆☆☆
- 10.7 Certificate 不含成交信息
- Rates notice 变更信息即使通过 GIPA 获得，也只有名字没有价格

### 结论：**放弃此路径**（除非有特殊定向需求）

---

## 12. Stamp Duty / OSR（Revenue NSW）⭐（不推荐）

### 调研结论
- Revenue NSW（原 OSR）管理印花税（transfer duty）
- **无公开索引**可查询印花税缴纳记录
- 印花税金额可反推成交价（通过公开的 duty calculator），但前提是知道成交发生
- 无批量数据发布
- 个人可以通过 MyServiceNSW 查自己的 duty transaction，但无法查他人

### 反推准确度：★☆☆☆☆
- 即使能获取，也只是确认成交已发生
- 无独立数据源价值

### 结论：**放弃此路径**

---

## 推荐实施策略

### Phase 1: 核心数据基座（免费，立即可做）

1. **下载 NSW VG Property Sales Data**
   - 从 `nswpropertysalesdata.com` 下载 6 年 CSV
   - 或从官方 Portal 下载完整历史（1990 起）
   - 导入 PostgreSQL/PostGIS 或 QGIS

2. **下载 VG Bulk Land Value Data**
   - 从 Valuation Services Portal 月度下载
   - 与 sales data 关联（通过 property ID）

3. **建立周末拍卖结果抓取流程**
   - 每周一自动抓取 Domain/REA 拍卖结果
   - 按 suburb 归档
   - 与 VG 数据交叉（拍卖结果可提前于 VG 数据 1-2 个月）

### Phase 2: 信号增强（免费，需开发）

4. **接入 NSW Planning Portal DA Open API**
   - 定期拉取新 DA（按 LGA/suburb）
   - 建立分类规则：哪些 DA 类型 → 可能是换手后行为
   - 与 VG 数据时间序列交叉，验证假设

5. **建立地址索引**
   - 用 NSW LRS 免费 title reference ↔ address 查询
   - 构建目标区域的 property ↔ title 映射表
   - 为后续定向 title search 做准备

### Phase 3: 精确验证（付费，定向）

6. **对高价值目标做定向 Title Search**
   - 通过 InfoTrackGO 或 Fynd（~$20/次）
   - 获取精确的 transfer dealing 信息
   - 验证 Phase 1-2 的推断

7. **评估 Domain API 商用可行性**
   - 如果需要近实时数据，Domain API 是最佳来源
   - 需与 Domain 商务团队洽谈费用

### Phase 4: 市场趋势校准

8. **订阅 PEXA Property Insights Report**
   - 季度下载免费报告
   - 校准宏观成交量趋势
   - 判断某时段数据是否异常

---

## 数据交叉验证矩阵

| 目标信息 | 主数据源 | 验证源 1 | 验证源 2 |
|---------|---------|---------|---------|
| 成交价 | VG Sales Data | Domain 拍卖结果 | Title Search（付费） |
| 成交时间 | VG Sales Data | DA lodgement 日期 | Domain sold listing |
| 新业主身份 | Title Search（付费） | DA 申请人 | — |
| 换手信号（无价格） | DA 新建/拆除 | VG Sales（确认成交） | Domain listing 下线 |
| 土地价值变化 | VG Land Value Data | Council valuation | Domain property profile |
| 宏观市场趋势 | PEXA 报告 | VG 统计 | Domain auction clearance rate |

---

## 关键 URL 汇总

| 资源 | URL | 类型 |
|------|-----|------|
| VG Property Sales (便捷版) | https://nswpropertysalesdata.com | 免费 CSV 下载 |
| VG Property Sales (官方) | https://valuation.property.nsw.gov.au/embed/propertySalesInformation | 免费 Portal |
| VG Bulk Land Value | Valuation Services Portal | 免费 CSV 月度 |
| NSW Planning Portal DA API | https://www.planningportal.nsw.gov.au/opendata/dataset/online-da-data-api | 免费 API |
| DA Radar (第三方 DA) | https://da-radar.com.au/nsw | 免费浏览 |
| Domain 拍卖结果 | https://www.domain.com.au/auction-results/sydney | 免费 |
| REA 拍卖结果 | https://www.realestate.com.au/auction-results/nsw | 免费 |
| Domain Sold Listings | https://www.domain.com.au/sold-listings/sydney-region-nsw | 免费 |
| Domain Property Profile | https://www.domain.com.au/property-profile | 免费 |
| Domain Developer API | https://developer.domain.com.au | 付费 |
| NSW LRS Online Portal | https://online.nswlrs.com.au | 免费/付费 |
| InfoTrackGO Title Search | https://infotrackgo.com.au/property/title-search | 付费 ~$20 |
| Fynd Title Search | https://www.fynd.info/products/title-search | 付费 ~$20 |
| Old Listings | https://www.oldlistings.com.au | 免费 |
| PEXA Insights | https://www.pexa-group.com/content-hub/property-insights-and-reports | 免费 PDF |
| Quiet Listings | https://www.quietlistings.com.au | 免费/ freemium |
| UNSW City Futures VG Data | https://citydata.ada.unsw.edu.au/dataset/nsw-valuer-general-property-sales | 免费 |
| Apify Domain Scraper | https://apify.com/haketa/domain-com-au-scraper | 付费（平台） |

---

*调研完成。核心结论：NSW VG Property Sales Data 是被严重低估的免费金矿——它就是 CoreLogic 的上游数据源之一。配合 DA Open API 和拍卖结果，可以构建完整的房产换手追踪体系。水电/OSR/council rates 等路径因隐私法限制基本不可行。*
