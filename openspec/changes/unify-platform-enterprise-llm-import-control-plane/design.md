## Context

当前 `yeshuangmingpian` 是唯一技术主干：React/Vite 管理端与公开名片端、FastAPI、PostgreSQL/RLS、Redis/Celery、MinIO 和当前 `knowledge_import` 已形成可运行基础。平台工作区目前只有运营概览和企业开通/列表，企业工作区已有访问、对话、线索、知识、内容和名片等主体能力；LLM 仍主要由进程启动环境变量决定，缺少平台可维护、可测试、可切换且不泄密的配置闭环。

三份产品文档用于约束业务目标和一期角色范围；参考仓库 `shuzimingpian` 只作为平台/企业控制台与 LLM 多 profile 的交互和安全语义样板。用户已重复锁定：资料导入必须继续使用当前仓库 `knowledge_import`，不得移植参考仓库的 `document_import` 或 Docling/OCR；最新明确需求是平台还需用该现有链路实现“导入资料辅助生成企业”。

根 `DESIGN.md` 已冻结为 `inherit`。本变更是 Feature DESIGN Delta：保留当前克制、清晰、可信的组件语言；吸收参考项目的平台琥珀/企业蓝工作区识别、分组导航和企业详情结构，但修复其移动端裁切、原始事件码、零值长表和演示型 KPI 问题。

## Goals / Non-Goals

**Goals:**

- 第一实施批先完成安全可用的 `chat_main` 多 profile LLM 配置，并让真实访客 Chat 无需重启采用当前主配置。
- 在一个管理应用中形成角色隔离的平台与企业工作区，完善平台企业下钻、开通交付、聚合运营、任务/审计/健康和公开名片跳转。
- 在平台开通与交付中增加资料辅助建企：临时企业范围隔离导入，LLM 基于解析草稿生成带来源建议，人工确认后只激活企业、管理员和内容草稿；名片由企业管理员后续创建。
- 保留企业端现有业务模块和 API，通过导航重组、状态完整性与逐名片公开预览提升可用性。
- 保持当前 `knowledge_import` 唯一导入链路、端点、解析/Worker、默认草稿和租户隔离合同，并用少量真实证据确认 UI 改造后仍正常。
- 冻结开发、Local Compose 和生产反代三类端口/base-path 合同，避免参考仓库路由实现破坏 `/c/admin/` 部署。

**Non-Goals:**

- 不引入或修复 `document_import`、Docling、MinerU、独立 OCR 服务、Source Units 或第二套原始文档解析链路；辅助建企的 LLM 只读取当前 `knowledge_import` 已解析草稿并产生不可自动生效的建议。
- 不把普通资料导入改为依赖 LLM；LLM 未配置时文件解析和草稿生成仍可工作，资料辅助建企退化为人工填写。
- 不配置或重构 Embedding/Rerank，不新增 `document_extraction` capability，不做自动模型故障转移或按企业模型路由。
- 不做平台模拟登录、企业激活后的代编辑、企业删除、完整 CRM、计费、商会独立控制台或工作区手动切换；平台只可在未激活的开通会话中审核初始化建议。
- 不拆分新的 `platform-web`，不新增外部服务或端口，不整目录复制参考仓库样式/迁移。

## Decisions

### 1. 当前仓库是唯一实现真源，参考仓库按 adopt/rewrite/reject 使用

- **Adopt**：平台分组 IA、企业详情/全部名片、服务端 `share_url`、平台琥珀/企业蓝身份、LLM profiles 的密钥/版本/测试/激活语义，以及资料建企向导的分步交互目标。
- **Rewrite**：`routing.ts`、`AppShell.tsx`、平台迁移、企业开通页、任务中心和所有跨租户 API；必须保留当前 `APP_BASE_PATH/appHref`、RLS 与当前迁移头。
- **Reject**：参考仓库所有 `document_import*` 前后端/Worker、Docling/OCR、直接读取原始文件的 LLM 抽取、相关迁移和基础设施改动。
- **Defer**：Embedding/Rerank 动态绑定、card-scoped RAG、自动 failover、复杂任务重试。

实施时如需读取参考代码，使用其已提交 HEAD `f625ec8` 的文件内容作为证据，不从包含未提交导入实验的工作区复制目录。

### 2. LLM 配置是第一业务工作包，直接创建最终多 profile 数据模型

当前主干没有平台 LLM 单例表，因此不复制参考仓库“先单例、再多 profile”的迁移链。直接从当前迁移头创建最终 `platform_llm_profiles` 模型：命名唯一、随机 UUID、AES-GCM 密文 key、`key_hint`、enabled、唯一 active、版本、更新人和时间。数据库约束加事务锁保证零 profile 时零 active、存在 profile 时恰好一个 active。

平台提供列表、创建、更新、测试和激活接口；无 DELETE。编辑必须携带 `expected_version`，切换主配置还携带 UI 所见 active ID，过期返回 409。空 key 保留原密文，API 永不返回密文/明文，审计只记录元数据。

低风险通用问答和 FAQ 快速直答都由平台管理员在每个 LLM profile 上控制，不下放企业端。`allow_general_answers` 只放宽缺少企业证据的低风险自由问答，高风险、价格和明确禁止内容仍走严格证据门；`faq_fast_path_enabled` 只在命中已发布且高置信 FAQ 时直接返回标准答案并跳过模型。两项默认关闭，保存后由每次请求的有效配置解析器即时读取，不触发容器重构或重启。

连接测试使用 OpenAI-compatible `/models`、短超时、禁重定向、禁自动重试和脱敏响应。Base URL 拒绝 credentials/query/fragment；生产强制 HTTPS，并沿用项目出站/DNS 安全策略。

运行时把启动时固定 orchestrator 改为可按请求读取有效 `chat_main` 配置并安全构造 provider；后续性能需要时才增加短 TTL。数据库零 profile 时允许现有环境变量兜底；一旦存在 profile，显式停用 active profile 就让 AI 不可用，禁止静默换供应商。公开 `ai_assistant.available` 与真实 Chat 使用同一解析器。当前导入解析不读取该配置。

### 3. 单管理应用、自动工作区归属和前后端双重守卫

继续使用 `admin-web`。平台和企业账号登录后按唯一 membership 自动进入对应工作区，不提供手动身份切换。前端在路由层校验 role/permission，越权进入显示明确 403 页面；后端仍是最终授权真源。

平台导航：

- 系统准备：未配置时在总览顶部显示 LLM readiness 阻断卡并直达配置。
- 工作台：运营总览。
- 企业运营：企业中心、开通与交付（含资料辅助建企）。
- 用户与访问：员工概览、访客中心。
- 平台运维：任务中心、操作审计、服务状态。
- 平台设置：LLM API 配置。

企业导航：

- 工作台：业务概览。
- 客户经营：访问、访客画像、AI 对话、机会、线索。
- AI 与知识：资料导入、FAQ、知识缺口、禁答、索引健康。
- 内容与名片：名片、企业资料、产品、案例。
- 企业治理：成员、隐私、导出；通知收纳到顶栏入口。

优先保留现有路由和页面组件，仅移动导航归组；需要新增的平台静态路由继续通过 current base-path helper 生成链接。

### 4. 平台使用窄跨租户读取模型，不进入企业私域

平台 API 只返回白名单运营字段和聚合：企业/开通状态、资料完成度、员工/名片数量、名片发布状态、访问/对话/线索数量、异常任务与服务健康。禁止返回访客 PII、对话正文、线索正文、企业知识正文、联系人私密字段或任何密钥。唯一例外是资料辅助建企的创建者在会话未激活期间可读取该会话的导入草稿和结构化建议；确认或取消后平台不得继续读取企业知识正文。

企业中心列表与开通表单拆页。桌面企业详情使用宽抽屉；小于等于 720px 使用全屏详情 sheet，指标转为 1-2 列，名片转纵向记录卡。平台不提供“进入企业后台”或模拟登录。

企业暂停/恢复使用明确状态机、reason、expected version、二次确认和审计。任务中心第一批以 PostgreSQL/outbox/knowledge import 状态为只读投影；在当前幂等合同未冻结前不开放人工重试，避免照搬参考项目只适用于 `document_import` 的重试逻辑。

### 5. 企业官方名片、员工名片与同一真实公开页

名片数据合同增加明确业务类型：`enterprise` 归企业所有且不绑定员工，`employee` 归具体员工所有且必须绑定当前企业有效成员。企业管理员可管理两类名片；名片主人只管理本人 `employee` 名片。企业控制台将两类名片分区，企业名片区提供不依赖员工的创建、编辑、发布和下线，员工名片区保留按员工管理。

平台企业详情和企业名片列表都按类型显示每张名片，不引入“主名片”。只有 `published` 且 API 返回 `share_url` 时显示“打开公开页”，使用新标签与 `noopener noreferrer`；草稿/停用项明确无公开页。前端不得自行拼 `/c/{slug}`。

公开端继续使用当前 `/c/:slug` 与 `/api/v1/public/cards/{slug}` 合同，不采用文档草案的 `/card/:slug`，也不创建后台专用伪预览页面。

### 6. 导入原链路保持真源，并增加受控的资料辅助建企编排

保留以下真源：`KnowledgeImportPanel`、`knowledgeImportsApi`、`knowledge_ops.py` 的 `/admin/knowledge/imports` 端点、`knowledge_import.py`、`knowledge_import_store.py` 和 `cf_worker.knowledge_imports`。

保持支持格式和 5 文件/10 MiB 单文件/25 MiB 批次限制；默认生成草稿，只有显式权限和选择才自动发布。企业概览可增加导入失败/待审核数量与入口，但不得改普通企业 endpoint 名称、状态枚举或 Worker 领取。LLM 未就绪时导入解析仍可完成；如后续索引/AI 不可用，UI 分别显示解析、草稿/发布和 AI readiness，不能把部分完成显示为全部成功。

资料辅助建企采用受控五步编排：

1. 平台管理员提供企业主体类型、信用代码或例外身份、管理员账号/显示名；系统生成内部标识和不可登录、不可公开、普通列表不可见的临时 tenant/company、版本化开通会话与禁用凭据。临时密码只在确认时由服务端生成。
2. 专用平台开通入口只接收 `onboarding_session_id`；服务端从会话推导临时 tenant/company，再复用当前 `knowledge_import` 格式校验、MinIO、store/parser、批次状态和 Worker。客户端不能选择任意目标租户，平台也不获得企业登录会话。
3. 文件解析成功后，已激活的 `chat_main` profile 只读取解析草稿文本，生成企业名称、行业、简介、网站和产品/案例/FAQ 内容建议。每个建议保存来源文件/草稿、置信提示和生成版本；文档内容按不可信输入处理，不执行其中指令、不跟随 URL、不读取或输出密钥。
4. LLM 不可用或生成失败时保留导入草稿并退化为人工填写。任何建议均不得创建账号、激活企业、自动发布知识或名片。
5. 平台管理员逐字段审核并携带 `expected_version` 确认；同一事务幂等激活 tenant/company、管理员 membership/credential 并生成一次性临时密码，不创建任何名片。导入知识仍保持草稿，交由企业管理员按原权限审核发布并自行创建名片。确认、取消或过期后，平台失去正文访问权；物理清理由独立保留策略处理。

### 7. 视觉只做功能级增量，修复参考界面的可用性缺陷

平台使用克制琥珀识别，企业使用现有蓝色，颜色只作用于品牌标记、选中态和关键状态；共享 Fluent、8px 圆角、Panel/Table/StatusBadge、可见焦点和错误反馈。拒绝渐变玻璃、多色 KPI、雷达图和无真实数据的装饰图表。

总览首屏优先待办/异常、开通进度、已发布名片、LLM/导入 readiness；规模数据次级。资料辅助建企使用清晰的“初始化 → 上传解析 → 生成建议 → 人工确认 → 完成”步骤条，桌面双栏来源/表单，小于等于 720px 改为单列且主动作固定可见。移动端不渲染 30 天零值长表。任务事件码翻译为业务标签，原始码只在详情。审计和名片表在窄屏转记录卡，禁止主动作被横向裁切。

### 8. 端口和 base path 分环境冻结，不照搬参考路由

- 开发：Card 4173、Admin 4174、API 8000、可选本地 Embedding 8010、Worker health 8020。
- Local Compose：Card 8080、Admin 8081、API 8000、Worker health 8020、PostgreSQL 5432、Redis 6379、MinIO 9000/9001。
- 生产：宿主机入口 127.0.0.1:18080 → gateway 8080；公开端 `/c/`、管理端 `/c/admin/`、API `/c/api/`，不把 8081 作为独立公网入口。

计划阶段补齐 `.codex/harness/contracts/runtime-ports.json`，实现不得新增端口或改变以上 base path；前端链接必须通过 current `APP_BASE_PATH/appHref` 和服务端 `share_url`。

### 9. 验证采用风险聚焦而非全量跑分

每个工作包只运行受影响的前端/API/Worker focused tests、管理端 build 和 API 合同检查。最终真实链路限制为：LLM 保存/测试/激活并完成一次 Chat；资料辅助建企上传一个小型支持文件、生成/人工修订建议并确认出唯一企业；平台企业详情打开公开名片；企业端打开同一名片；普通企业导入上传一个小型支持文件到草稿；一个失败/越权路径。UI 只验证代表性 desktop 与 390px 页面、一次键盘焦点 spot-check。

不运行完整性能套件、全量 RAG benchmark、全页面视觉回归、参考仓库全测试或 19 MiB Docling golden path，除非 focused evidence 暴露相关故障。

## Risks / Trade-offs

- [动态 LLM 配置与启动时 orchestrator 冲突] → 把 provider 解析收口到单一 runtime resolver，并用切换后真实 Chat 证明无需重启。
- [行为开关误放宽回答边界] → 开关归平台 profile、默认关闭、逐请求读取；通用问答仅覆盖低风险，FAQ 快速路径只接受已发布高置信命中，高风险门禁不受影响。
- [密钥泄漏或 SSRF] → 字段加密、只写不回显、URL/DNS/HTTPS 校验、禁重定向、脱敏审计和平台角色 403。
- [跨租户读取扩大] → 新建窄 response schemas/store queries 与禁止字段测试，不复用企业私域 CRUD。
- [多 profile 并发切换不一致] → partial unique constraint、事务/advisory lock、expected version 与 active ID 冲突检测。
- [平台页面范围过大] → 按 LLM → 核心企业闭环 → 企业整理 → 聚合/运维分批实施，同一 change 内按硬依赖排序。
- [导航重组造成现有 deep link 回归] → 尽量保留现有路径，只改变分组；base-path 和直接 URL 冒烟列为硬门。
- [控制台改造破坏资料导入] → 导入源码原则上不重写，只补状态接线；用真实小文件和 focused tests证明。
- [临时企业范围造成孤儿或越权] → 临时资源默认不可登录/公开/普通查询，目标范围由服务端会话绑定，确认使用版本与幂等键，取消/过期软锁定并独立审计。
- [不可信资料提示注入或生成错误企业信息] → LLM 只处理解析草稿、禁工具/外链/密钥上下文，逐字段保存来源并强制人工确认；生成失败退化为手填。
- [参考迁移污染当前数据库] → 从当前迁移头重新设计少量迁移，禁止复制参考编号和含 `document_import` 的 SQL。
- [验证过轻漏掉跨端问题] → 保留五条高价值真实链路和关键 403/secret 硬门；只有这些失败时扩大回归。

## Migration Plan

1. 冻结路由、权限、平台白名单、LLM profile schema、端口/base-path 和导入不变合同。
2. 从当前迁移头新增最终 LLM profiles 迁移，完成安全 API、runtime resolver、平台 UI 与一次真实 Chat；环境变量保留零 profile 回滚路径。
3. 新增版本化资料辅助建企会话和临时企业范围，接入当前 `knowledge_import`，实现基于解析草稿的带来源 LLM 建议与人工原子确认。
4. 新增平台窄读取/治理合同、总览、企业中心/详情、开通与交付、名片公开页入口。
5. 重组企业导航，补名片公开入口、LLM/导入 readiness 与完整状态；保留现有业务页面和导入实现。
6. 增加员工/访客聚合、只读任务中心、审计与服务状态；如需企业暂停/恢复，在状态机和审计测试通过后启用。
7. 运行 focused tests、build、合同检查和六条代表性 smoke；失败只从对应工作包扩大验证。

回滚顺序与上线相反。前端页面可先隐藏；平台新 API 可关闭路由；数据库 profiles 数据保留，运行时在零 profile 或禁用新 resolver 时仍可回到环境配置。任何回滚不得删除企业、知识导入批次或密文配置数据。

## Open Questions

无阻塞性产品问题。资料辅助建企使用 `chat_main` 当前激活 profile 对已解析草稿生成建议，不新增独立文档抽取 profile；Embedding/Rerank、原始文档抽取 capability 和自动故障转移明确留到独立变更。

## 11. P0/P1 platform and enterprise IA convergence

Platform and enterprise navigation are separate products inside one admin shell. Platform uses multi-company operations domains; enterprise uses Workbench, Customer Growth, Content and Intelligence, Enterprise Governance and More Tools. Only the active enterprise work domain expands. Stable routes, permissions and commercial feature IDs remain authoritative.

Platform enterprise detail uses `/platform/enterprises/:companyId/:section`; enterprise detail uses typed matchers for visits, visitor profiles, conversations, opportunities, contextual leads and products. Compatibility redirects preserve old aggregate URLs and base-path behavior. The full platform detail drawer is retired; no section may use mock data.

## 12. Enterprise identity and provisioning

Tenant/company UUIDs remain immutable primary and RLS identifiers. A unique `business_tenant_key` is the operator-visible tenant identity. Domestic companies derive it from normalized social-credit code; exempt subject types receive a stable server-generated key. Company legal name, outward short name and subject type are explicit.

Enterprise administrators may update identity with optimistic version, uniqueness validation and audit. Changing a social-credit code updates the business key but never rewrites UUID foreign keys or historical ownership.

Direct and document-assisted provisioning share one cardless result: tenant, company, administrator membership/credential, one-time temporary password, isolated imports/drafts and starter entitlements. Historical onboarding rows may retain an initial card; new rows do not create one. Enterprise users create and publish cards later.

## 13. Operational metrics and tasks

Overview, enterprise list and detail reuse one server-owned metric vocabulary. Enabled count and 30-day active count are separate. Operational tasks normalize onboarding, imports, content review, lifecycle risk and service-validity risk; successful outbox delivery is excluded. Timeline and company views share filters and never expose generic technical retry.

## 14. Enterprise settings and notification noise

Company profile stores identity and outward presentation only. Answer boundaries move to answer policy; notification delivery preferences move to notification settings; personalization consent/version/retention move to data and privacy. Enterprise model credentials remain P2.

Consented leads and high-intent activity may notify in real time. Ordinary visits are summarized by an idempotent daily digest rather than per-visit pushes.
