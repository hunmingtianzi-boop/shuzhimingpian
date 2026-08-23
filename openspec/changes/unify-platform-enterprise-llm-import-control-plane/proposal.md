## Why

当前仓库已经具备稳定的多租户名片、企业管理、知识导入与公开访问基础，但平台控制台仍偏向企业开通，缺少日常运营、企业下钻和统一 LLM 配置；企业控制台也需要把名片公开预览与现有资料导入串成更清晰的工作闭环。现在需要以当前仓库为唯一技术主干，吸收参考项目中经过验证的平台/企业控制台交互，同时明确拒绝其不稳定的文档导入实验链路。

## What Changes

- 将平台 LLM 配置放在第一实施阶段：支持多个命名的 OpenAI-compatible Chat 配置，安全保存密钥、测试连接、启用/停用并明确选择唯一主配置，访客 AI 无需重启即可使用当前主配置。
- 扩展平台控制台为分组运营工作区：运营总览、企业中心、开通与交付、员工/访客聚合、任务中心、操作审计、服务状态和 LLM 配置。
- 在平台“开通与交付”中增加资料辅助建企：创建隔离的临时企业范围，复用当前 `knowledge_import` 解析资料，由已激活 LLM 基于解析草稿生成带来源的企业身份与内容建议，人工确认后再正式激活企业；平台不创建名片。
- 平台企业详情展示白名单运营指标、开通进度和全部名片；仅已发布名片显示服务端生成的公开页链接，平台不代登录企业、不读取企业私密正文。
- 完善企业控制台的信息架构和名片管理，使企业管理员能在原有资料、知识、访客、对话、线索和名片工作流之间清晰导航，并逐张打开真实公开名片页。
- 资料导入继续且仅使用当前仓库的 `knowledge_import` API、解析器、存储、Worker 与审核/发布语义；辅助建企只在其解析草稿之上生成可审核建议，不引入参考项目的 `document_import`、Docling/OCR 或新的原始文档抽取链路。
- 冻结当前仓库既有运行端口，不增加新服务或外部运行依赖。

## Capabilities

### New Capabilities

- `platform-llm-profiles`: 多个安全存储的主 Chat LLM 配置、唯一主配置、连通性测试、运行时选择和兼容环境兜底。
- `platform-operations-console`: 平台运营总览、企业中心/详情、开通交付、员工/访客聚合、任务、审计和服务状态。
- `document-assisted-enterprise-onboarding`: 平台通过当前资料导入链路创建隔离开通草稿、生成带来源的企业初始化建议，并在人工确认后原子激活企业。
- `enterprise-management-console`: 企业控制台的信息架构、角色安全导航和关键业务入口一致性。
- `knowledge-import-assurance`: 保持当前 `knowledge_import` 链路为唯一资料导入实现，并保证格式、草稿、租户隔离、状态和错误反馈合同。
- `cross-surface-card-preview`: 平台与企业控制台逐张查看名片状态并打开服务端生成的已发布公开页。

### Modified Capabilities

<!-- 当前 openspec/specs/ 尚无既有能力规范；本变更只新增能力。 -->

## Impact

- Admin Web：平台分组导航与页面、资料辅助建企向导、企业工作区导航、LLM 配置列表/抽屉、企业详情、名片公开预览、现有导入状态体验和响应式样式。
- API：扩展 `/api/v1/platform/*` 窄投影、治理和资料辅助建企接口，新增平台 LLM profiles 合同；保留企业 `/api/v1/admin/*` 与公开名片 API 现有边界。
- 数据：从当前迁移头新增干净的平台 LLM profiles、受版本控制的开通草稿与平台运营所需迁移，不复制参考仓库迁移编号或中间单例方案。
- AI Runtime：主 Chat 从唯一启用 profile 解析；只有数据库零 profile 时才允许环境配置兜底。Embedding/Rerank 不在本变更中统一配置。
- 导入：不替换 `knowledge_import` 实现，不新增 Docling/OCR 或第二套原始文档解析依赖；辅助建企的 LLM 只读取已解析草稿并输出不可自动生效的结构化建议。
- Runtime：本地开发与 Local Compose 沿用当前管理端、公开名片、API、Worker health 和基础设施端口；生产继续通过现有 18080 gateway 与 `/c/`、`/c/admin/`、`/c/api/` base path，不新增公网端口。

## P0/P1 convergence (2026-08-23)

- Platform navigation converges on overview, enterprise management/onboarding, actionable tasks, health and platform AI settings. Employee/visitor aggregates fold into overview; audit remains a protected diagnostic deep link.
- Enterprise detail becomes a refreshable route with eight operational sections; the full-detail drawer is removed.
- New enterprise provisioning creates identity, isolated scope, administrator delivery and default entitlements only. It creates no card, card slug or public URL.
- Legal company name, outward short name, subject type and a unique business tenant identifier are separated from immutable tenant/company UUIDs. Domestic enterprises use the normalized social-credit code as the business tenant identifier.
- Platform tasks become normalized actionable work rather than successful outbox events.
- Enterprise navigation uses work domains with progressive disclosure and preserves real object/detail relationships.
- Company identity, answer policy, notification preferences and data/privacy settings are separated. Enterprise BYOK/model routing remains P2; associations and billing remain P3/P4.
