# 04 API 与事件契约

版本：V1.0  
协议：HTTPS + JSON；AI 输出使用 Server-Sent Events（SSE）

## 1. 总体约定

- 外部 API 前缀：`/api/v1`；内部健康检查不放在公开网关。
- `packages/contracts/openapi.json` 是前后端契约事实源，生成客户端后不得手工改生成代码。
- 字段使用 `snake_case`；时间使用 ISO 8601 UTC，例如 `2026-07-10T08:30:00Z`。
- ID 使用字符串形式 UUID；金额如后续加入，使用最小货币单位整数。
- 单对象成功响应：`{"data": {...}, "meta": {...}}`。
- 列表成功响应：`{"data": [...], "meta": {"next_cursor": "...", "has_more": true}}`。
- 错误响应统一格式：

```json
{
  "error": {
    "code": "KNOWLEDGE_NOT_READY",
    "message": "企业知识库正在更新，请稍后重试",
    "details": {},
    "request_id": "019..."
  }
}
```

对访客暴露的 `message` 使用安全文案；内部错误、供应商信息和堆栈只写日志。

## 2. 鉴权与作用域

### 2.1 管理端

- 短期 Access Token（建议 15 分钟）+ 可撤销 Refresh Token（建议 7 天，滚动更新）。
- Refresh Token 使用 HttpOnly、Secure、SameSite Cookie；数据库只保存哈希。
- Access Token 只包含身份和会话 ID，不信任前端提交的租户/企业权限。
- 每个请求从数据库/短期权限缓存解析 membership，建立服务端请求作用域。
- 登录、刷新、退出、会话撤销必须有审计和速率限制。

### 2.2 访客端

- 首次 `POST /public/cards/{slug}/visits` 创建卡片范围内的匿名访客会话并返回短期签名 Token。
- Token 只允许访问对应名片、企业和本人会话；不能用作管理端身份。
- 公开 GET 可匿名，但只能获取已发布字段；对话、留资、隐私请求必须使用会话 Token。
- `company_id`、知识范围和名片归属全部由服务端从 `slug`/会话推导。

## 3. 公开访客 API

| 方法 | 路径 | 说明 | 鉴权/限制 |
|---|---|---|---|
| GET | `/public/cards/{slug}` | 名片、企业摘要、精选产品/案例、AI 状态、隐私版本 | IP/card 限流；仅公开字段 |
| GET | `/public/cards/{slug}/products` | 已发布产品分页 | 公开；游标分页 |
| GET | `/public/cards/{slug}/products/{id}` | 产品详情 | 必须属于该 card 的 company |
| GET | `/public/cards/{slug}/cases` | 已发布案例分页 | 公开；游标分页 |
| POST | `/public/cards/{slug}/visits` | 创建访问会话，记录来源 | 幂等；返回 visitor session token |
| POST | `/public/cards/{slug}/consents` | 记录 chat/lead 同意 | 会话 Token；保存政策版本与证据 |
| POST | `/public/cards/{slug}/conversations` | 创建 AI 会话 | 要求 chat notice；幂等 |
| POST | `/public/conversations/{id}/messages:stream` | 发送问题并流式接收回答 | SSE、会话 Token、严格限流 |
| POST | `/public/cards/{slug}/leads` | 主动留资/更新本人资料 | 明确 lead consent；幂等；风控 |
| POST | `/public/privacy-requests` | 查询、更正、删除/撤回申请 | 验证联系方式或人工核验 |

“主动问候”是对话界面内由系统展示的欢迎语/推荐问题，不等于在访客未授权前发送外部微信消息。

## 4. 管理端 API

### 4.1 身份

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/auth/login` | 账号密码/验证码登录，具体方式由待确认项冻结 |
| POST | `/auth/refresh` | 滚动刷新并撤销旧 Refresh Token |
| POST | `/auth/logout` | 撤销当前会话 |
| GET | `/auth/me` | 当前用户、membership 和权限 |

### 4.2 企业、内容与名片

| 方法 | 路径 | 功能 |
|---|---|---|
| GET/PUT | `/admin/company/profile` | 获取/更新当前企业资料 |
| GET/POST | `/admin/products` | 产品列表/创建 |
| GET/PATCH/DELETE | `/admin/products/{id}` | 详情/更新/归档 |
| POST | `/admin/products/{id}:publish` | 发布新版本并触发索引 |
| GET/POST | `/admin/cases` | 案例列表/创建 |
| GET/PATCH/DELETE | `/admin/cases/{id}` | 详情/更新/归档 |
| POST | `/admin/cases/{id}:publish` | 发布并索引 |
| GET/POST | `/admin/faqs` | FAQ 列表/创建 |
| GET/PATCH/DELETE | `/admin/faqs/{id}` | 详情/更新/归档 |
| POST | `/admin/faqs/{id}:publish` | 发布并索引 |
| GET/POST | `/admin/forbidden-topics` | 禁答规则列表/创建 |
| PATCH/DELETE | `/admin/forbidden-topics/{id}` | 修改/停用 |
| GET/POST | `/admin/cards` | 名片列表/创建 |
| GET/PATCH | `/admin/cards/{id}` | 名片详情/更新 |
| POST | `/admin/cards/{id}:publish` | 发布名片 |
| POST | `/admin/cards/{id}:deactivate` | 停用公开访问 |

CRUD 更新使用 `If-Match` 或请求体 `version` 实现乐观锁；冲突返回 409，禁止最后写入者静默覆盖。

### 4.3 访客、对话、纪要和线索

| 方法 | 路径 | 功能 | 权限 |
|---|---|---|---|
| GET | `/admin/dashboard` | 当前作用域聚合指标 | 企业管理员看企业，主人看本人 |
| GET | `/admin/visits` | 访问列表 | 按作用域过滤 |
| GET | `/admin/conversations` | 对话列表 | 默认不返回正文 |
| GET | `/admin/conversations/{id}` | 对话、AI run 和引用 | 敏感读取审计 |
| POST | `/admin/conversations/{id}:summarize` | 人工触发/重试纪要 | 幂等；受限操作 |
| GET | `/admin/summaries/{id}` | 纪要详情 | 同对话权限 |
| GET | `/admin/leads` | 线索列表 | 企业/本人作用域 |
| GET/PATCH | `/admin/leads/{id}` | 详情、状态、负责人、优先级 | 乐观锁 |
| POST | `/admin/leads/{id}/followups` | 追加跟进记录 | 只追加 |
| POST | `/admin/leads:export` | 创建异步导出任务 | P1；权限与审计 |

### 4.4 知识运营

| 方法 | 路径 | 功能 |
|---|---|---|
| GET/POST | `/admin/knowledge/documents` | 知识对象列表/创建 |
| GET/DELETE | `/admin/knowledge/documents/{id}` | 版本、状态、失败信息 / 从管理端与 AI 检索范围删除 |
| POST | `/admin/knowledge/documents/{id}/versions` | 创建草稿版本 |
| POST | `/admin/knowledge/versions/{id}:publish` | 审核发布并投递索引 |
| GET | `/admin/knowledge/index-jobs` | 索引任务状态 |
| POST | `/admin/knowledge/index-jobs/{id}:retry` | 失败任务幂等重试 |
| GET | `/admin/knowledge/chunks` | 调试查看切片，默认脱敏/截断 |
| GET | `/admin/knowledge/gaps` | 知识缺口列表 |
| PATCH | `/admin/knowledge/gaps/{id}` | 编辑 AI 草稿/补充字段 |
| POST | `/admin/knowledge/gaps/{id}:approve` | 审核通过并创建知识版本 |
| POST | `/admin/knowledge/gaps/{id}:reject` | 拒绝并记录原因 |
| POST | `/admin/knowledge:evaluate` | 运行离线评测任务 |

## 5. SSE 回答协议

请求示例：

```http
POST /api/v1/public/conversations/{id}/messages:stream
Authorization: Bearer <visitor-session-token>
Content-Type: application/json
Accept: text/event-stream
Idempotency-Key: 019...

{"content":"你们是否做制造业客户的 AI 项目？"}
```

事件类型：

```text
event: message.started
data: {"message_id":"...","request_id":"..."}

event: message.delta
data: {"text":"我们在制造业..."}

event: message.citation
data: {"citation_id":"...","label":"案例：某制造企业","source_type":"case"}

event: message.completed
data: {"message_id":"...","finish_reason":"stop","lead_prompt":false}

event: message.error
data: {"code":"MODEL_TIMEOUT","retryable":true,"request_id":"..."}
```

规则：

- 数据库成功建立 visitor message 后才发送 `message.started`。
- 客户端断开不等于任务取消；服务端按预算决定取消或继续，并保存最终状态。
- `message.completed` 前必须完成最终文本、安全检查和引用绑定的事务写入。
- 重复 Idempotency-Key 返回同一消息结果/状态，不重复扣费、不重复生成知识缺口。
- SSE 只返回访客可见的引用标签；原始内部片段只在授权后台查看。

## 6. 分页、查询与导出

- 时间序列表使用不透明 cursor，不用深分页 offset。
- 默认 `limit=20`，最大 100；服务端限制排序字段和筛选组合。
- 搜索对话正文和 PII 需要更高权限、明确用途并写审计。
- 大导出一律异步：创建任务 → Worker 生成加密文件 → 短期签名 URL → 自动过期清理。
- CSV 防公式注入；Excel/CSV 导出按用户权限脱敏。

## 7. 幂等、重试与并发

要求 `Idempotency-Key` 的操作：创建 visit/conversation/lead、发送消息、发布知识、触发索引/纪要/导出、外部通知。

- API 保存 `key + actor/scope + request_hash + response/status`。
- 同 key 不同请求体返回 `409 IDEMPOTENCY_CONFLICT`。
- Worker 采用至少一次投递；任务在数据库用业务幂等键抢占，不能只依赖 Redis 去重。
- 第三方超时只对可安全重试的请求指数退避；模型生成是否重试由 run 状态与预算决定。
- 发布/审核和线索更新使用乐观锁，禁止并发覆盖。

## 8. 统一错误码

| HTTP | 代码示例 | 含义 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 请求字段或业务状态不合法 |
| 401 | `AUTH_REQUIRED`, `TOKEN_EXPIRED` | 未认证/会话失效 |
| 403 | `PERMISSION_DENIED`, `CONSENT_REQUIRED` | 无作用域权限/未授权 |
| 404 | `RESOURCE_NOT_FOUND` | 不泄露其他企业资源是否存在 |
| 409 | `VERSION_CONFLICT`, `IDEMPOTENCY_CONFLICT` | 并发或幂等冲突 |
| 422 | `STATE_TRANSITION_INVALID` | 状态转换不允许 |
| 429 | `RATE_LIMITED`, `MODEL_BUDGET_EXCEEDED` | 限流/预算限制 |
| 503 | `KNOWLEDGE_NOT_READY`, `MODEL_UNAVAILABLE` | 可降级外部依赖故障 |

跨企业访问统一返回 404/403 的安全策略由接口类别决定，但必须写安全审计，不能在响应中暴露目标企业。

## 9. 异步领域事件

事件通过事务 Outbox 写入，名称和 Payload 带版本：

| 事件 | 生产者 | 主要消费者 |
|---|---|---|
| `knowledge.version.published.v1` | knowledge | 索引 Worker |
| `knowledge.index.completed.v1` | Worker | 通知、后台状态 |
| `conversation.closed.v1` | conversation | 纪要、意图/缺口分析 |
| `lead.created.v1` | lead | 站内通知、后续渠道 Provider |
| `visitor.privacy_deletion.requested.v1` | visitor | 清理编排、审计 |
| `card.deactivated.v1` | cards | 缓存失效、公开路由 |

每个事件包含 `event_id`、`event_type`、`occurred_at`、`tenant_id`、`company_id`、`aggregate_id`、`schema_version`、`trace_id`。消费者以 `event_id` 去重。

## 10. 上传安全

MVP 以结构化表单为主。开放文件上传后必须：

- 先向 API 申请上传；对象 key 由服务端生成并限制企业前缀。
- 使用白名单格式、大小限制、真实 MIME 检测、病毒扫描和解析沙箱。
- Office 宏、脚本、嵌入对象默认拒绝或隔离。
- 上传完成只进入 `quarantined`，扫描与解析成功后才能进入审核。
- 解析失败提供可操作错误，不将半成品切片发布到检索索引。
