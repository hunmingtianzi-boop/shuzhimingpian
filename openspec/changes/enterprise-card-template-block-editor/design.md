## Context

现有企业卡和员工卡共享 `cards` 表与公开页合同。企业卡已无员工 owner，员工卡通过 `owner_user_id` 绑定成员；但是当前 `Card` 同时保存展示姓名、职务和头像，员工身份更新无法自然反映到名片。企业公开端有一套固定区块，而后台只提供字段抽屉，不提供受控编排。

本设计保留卡的发布、版本、RLS、素材服务和公开 URL 合同，增加企业模板文档与成员资料投影。它不引入新的服务、端口或通用网页构建器。

## Goals / Non-Goals

**Goals:**

- 企业管理员可编辑一个有序的、类型受控的企业模板草稿并实时预览。
- 发布时生成与草稿隔离的公开快照；公开端只使用已发布快照。
- 企业基本资料来自公司记录，模板只保存展示/布局与可选覆盖字段。
- 员工名片默认从绑定 `User + Membership` 投影姓名、联系方式、职位和头像；名片只保存个人业务、AI 话术与内容选择。
- 每个媒体、案例和块在公司范围内验证，保持现有 RLS/资源隔离。

**Non-Goals:**

- 任意 HTML、JavaScript、CSS 或自由像素布局。
- 一期内视频上传、转码、第三方 iframe、自动抓取视频封面。
- 员工资料多份复制、跨企业复用同一成员资料、或自动修改已有已发布公开快照。

## Decisions

### 1. 企业模板是有 schema 版本的受控块文档

企业卡 `settings` 新增 `enterprise_template_draft` 和 `enterprise_template_published` 文档。文档包含 `schema_version`、`theme_key`、`blocks[]`；块都有 UUID、type、visible、payload 和显式 sort order。允许类型固定为 `rich_text`、`image_gallery`、`video_link`、`case_collection`、`faq`、`cta`、`ai_assistant`。

选择 JSON 文档而不是每种块建一张表，是因为块的顺序、可选性和将来的兼容类型需要原子版本化；JSON 仍通过 Pydantic 判别联合与服务端范围校验，不能被当成无结构 payload。

### 2. 发布写入不可变公开快照

草稿更新只修改 `enterprise_template_draft`。发布操作在乐观版本检查后，深拷贝并校验草稿到 `enterprise_template_published`，并保留 card 的 published/status 语义。公开读取只选择 published snapshot；未发布模板不能泄露预览资源。

这比直接读取草稿可靠，代价是发布流程要有明确的 check list。

### 3. 企业资料与模板表达分层

`Company.name`、`Company.industry` 和受控 company settings 是企业基本资料的真源；模板块引用这些资料或增加展示内容，不能再创建第二套企业主身份。企业卡仍保留兼容性字段，迁移为现有卡创建等价的默认模板。

### 4. 员工身份以 User + Membership 为真源

增加/扩展 member profile（职位、头像、个人业务摘要）到成员范围；姓名和私密联系方式仍来自 `User` 的现有加密字段。员工卡读取 owner membership 的投影，不能编辑这些身份字段；它只保存 AI 话术、推荐问法和个人业务内容覆盖。若成员不可用/不在公司范围，员工名片的更新和发布拒绝。

### 5. 媒体边界按风险分层

图片继续通过 `CardAssetStore` 上传，接受已有 JPEG/PNG/WebP 限制。视频一期采用 HTTPS URL + 已上传封面图；禁止 data URL、私网 URL、iframe 和任意脚本。案例块只保存公司范围内案例 ID 和展示选择，公开渲染时再次校验 published 状态。

## Risks / Trade-offs

- [旧企业卡缺少模板] → 迁移时生成默认模板；无法生成的卡保持草稿，提示管理员补齐。
- [JSON 结构漂移] → schema version、严格判别联合、服务器端归一化与版本化迁移。
- [资料被多个页面编辑] → 成员资料仅在成员管理入口编辑，卡编辑器只读展示身份字段。
- [外部视频变更或下线] → 必须有封面和安全 URL，公开端提供不可用降级状态。
- [公开快照与引用案例不同步] → 发布时冻结展示字段，公开读取再验证当前范围/发布状态并安全隐藏失效引用。

## Migration Plan

1. 添加成员资料和企业模板草稿/发布快照字段。
2. 为每张现有 enterprise card 从现有企业资料/目录生成兼容默认草稿和已发布快照（仅原卡已发布时）。
3. 将员工卡的身份字段回填至对应成员资料，之后员工卡读取投影。
4. 部署新 API 和编辑器；旧公共卡缺省走兼容渲染，直到每张卡有快照。
5. 回滚时停止写入新文档并回退到兼容投影，不删除快照或成员资料。

## Open Questions

- 视频域名 allowlist 首批是否只允许腾讯视频、哔哩哔哩和企业自有 HTTPS 域名？实现阶段以安全默认拒绝未知域名。
- 案例块是否应在发布时冻结案例摘要，还是只引用实时已发布案例？首版采用冻结展示字段 + 当前范围复核。
