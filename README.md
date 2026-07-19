# 创非凡数智名片

项目定位：面向多企业的数智名片生成与运行平台，以响应式 H5 为入口，承载企业展示、受控 AI 接待、访客行动和线索沉淀。

当前实现以通用渲染器为产品主体。所有新建企业名片统一使用“个人、企业、AI 制作”三页单屏结构，默认进入个人页。企业信息通过独立内容包或后台发布接口接入，运行时根据 tenant 选择企业实例。根地址和 `/c/template` 展示无真实企业品牌的通用模板，拓浙 AI 生态只是首个企业 seed，tenant key 为 `tuotu`。

核心纵向切片已经落地：PostgreSQL/pgvector 多租户模型、强制 RLS、员工认证、企业管理后台、知识草稿与原子发布、DeepSeek V4 Provider、混合检索、证据门控、可追溯引用、访客会话与 SSE 问答。文件解析 Worker、完整留资/纪要和线上评测运营仍按后续阶段开发。视频数字人、知识图谱和完整 CRM 不纳入 MVP。

## 本地体验

在仓库根目录启动通用 H5：

```powershell
pnpm web:dev
```

入口说明：

- `http://127.0.0.1:4173/`：通用模板。
- `http://127.0.0.1:4173/c/template`：通用模板的显式地址。
- `http://127.0.0.1:4173/c/tuotu`：首个企业 seed。
- `http://127.0.0.1:4173/?tenant=tuotu`：兼容查询参数的 seed 地址。

根路径不代表拓浙。未知 tenant 显示无品牌的安全状态，不能回退并泄露其他企业内容。通用模板中的品牌、业务、数据、链接和问答都是接入结构示意，不得直接作为企业正式页面发布。

生产构建与测试：

```powershell
pnpm web:test
pnpm web:build
```

启动数据库与真实 AI API（需要先安装 Docker，并把轮换后的模型密钥写入被忽略的 `.env.local`）：

```powershell
Copy-Item .env.example .env.local
# 编辑 .env.local：LLM_API_KEY 只供服务端读取；浏览器仅配置非敏感的
# VITE_API_BASE_URL，任何密钥都禁止使用 VITE_* 前缀
docker compose --env-file .env.local -f infra/compose.yaml up --build
```

Compose 会依次执行迁移、导入通用模板与 `tuotu` 初始知识，再启动 `http://127.0.0.1:8000`。前端启用真实问答时设置 `VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1`；未设置时继续使用浏览器内静态知识作为纯展示降级。

当前 Windows 开发机也提供已配置的本地运行命令：

```powershell
pnpm local:start
pnpm local:status
pnpm local:stop
```

`local:start` 会检查本机 PostgreSQL/pgvector 与 Redis，启动本地多语种 E5 向量服务，执行幂等迁移、初始资料导入和写时复制向量重建，再启动 API、访客 H5 与管理后台。首次缺少模型时会下载约 2 GB；后续复用 `%LOCALAPPDATA%\cf-ai-card-runtime\models`。六个服务都只监听 `127.0.0.1`，运行日志位于 `%LOCALAPPDATA%\cf-ai-card-runtime`。

- 访客端：`http://127.0.0.1:4173/c/tuotu`
- 企业管理后台：`http://127.0.0.1:4174/`
- API 文档：`http://127.0.0.1:8000/docs`

本地管理员由 `.env.local` 中的 `ADMIN_BOOTSTRAP_TENANT_SLUG`、`ADMIN_BOOTSTRAP_ACCOUNT` 和 `ADMIN_BOOTSTRAP_PASSWORD` 首次创建。密码不得写入仓库，生产环境必须改为密钥系统注入并在首次登录后轮换。启动时导入的数据只负责初始化，不会覆盖后台已修改的企业资料、名片配置或管理员已发布的知识版本。

不使用 Docker 时可单独运行后端单元测试：

```powershell
python -m venv services/api/.venv
services/api/.venv/Scripts/python -m pip install -e "services/api[dev]"
services/api/.venv/Scripts/python -m pytest services/api/tests
```

访客端位于 `apps/card-web/`，管理端位于 `apps/admin-web/`，API 位于 `services/api/`。数据库与问答实现见 [数据库与 AI 问答生产实现](docs/14-数据库与AI问答生产实现.md)，后台实现见 [企业管理后台与知识发布](docs/15-企业管理后台与知识发布.md)，通用架构见 [通用数智名片引擎与企业初始化](docs/12-通用数智名片引擎与企业初始化.md)，复制模板接入新企业见 [企业内容包模板使用说明](docs/13-企业内容包模板使用说明.md)，首个 seed 的事实源与禁答边界见 [拓浙 AI 生态 seed 内容包](docs/11-拓浙AI生态样板企业资料包.md)。

## 产品分层

```text
通用渲染器
  + 企业内容包
  + tenant 解析与发布版本
  + 受控知识与行动接口
  = 某个企业的数智名片实例
```

- 通用渲染器只负责页面模块、主题、响应式、无障碍、AI 助手 UI 和安全状态。
- 名片信息架构固定为个人主页、企业第二页和 AI 制作第三页。企业专属配置只能覆盖内容与素材，不能复制或替换页面骨架。
- 企业内容包保存品牌、业务、指标、素材、FAQ、来源、禁答和联系入口。
- tenant 解析器根据 `/c/{tenant}` 或 `?tenant={tenant}` 加载当前静态注册表中的内容包。
- `template` 是无真实企业事实的通用内容包示例。
- `tuotu` 是首个企业 seed，不是平台默认企业。

新增企业以 [`src/tenants/template/tenant.ts`](apps/card-web/src/tenants/template/tenant.ts) 为完整示例，只复制并修改企业内容包、租户素材和注册记录。不得修改 `App.tsx` 或 `styles.css`，不得在通用组件中按企业名称增加分支。

## 开工入口

1. 先阅读 [需求基线](docs/01-需求基线.md)、[系统架构](docs/02-系统架构.md) 和 [通用引擎架构](docs/12-通用数智名片引擎与企业初始化.md)。
2. 产品负责人关闭 [待确认事项](docs/08-决策与待确认.md) 中的 P0 阻塞项。
3. 技术负责人依据 [工程规范](docs/07-工程规范.md) 初始化依赖和本地环境。
4. 团队按 [开发计划与验收](docs/06-开发计划与验收.md) 执行 Sprint 0。
5. 企业接入人员使用 [样板企业资料采集模板](docs/10-样板企业资料采集模板.md) 收集资料，再按 [企业内容包模板使用说明](docs/13-企业内容包模板使用说明.md) 建立新租户。

完整文档索引见 [docs/README.md](docs/README.md)。

## 已确定的核心原则

- H5 先行，微信小程序、企微、钉钉和 CRM 集成分阶段接入。
- 所有页面、业务、知识、检索、文件、缓存和日志都必须绑定 tenant 作用域。
- 未知 tenant 不得回退到任一 seed，租户切换必须同步重置内容、主题、会话和埋点上下文。
- 模块化单体优先，API 与异步 Worker 分离，验证商业闭环后再按瓶颈拆服务。
- PostgreSQL 是业务事实源，pgvector 承担 MVP 向量检索，Redis 承担缓存与任务队列。
- AI 只基于该企业已审核知识回答，无依据时拒答，不自动报价、不作合同承诺。
- “越用越聪明”定义为知识缺口、人审和重新索引，不是自动训练或吸收访客内容。
- AI 回答、检索片段、模型调用、Prompt 版本和审核操作必须可追溯。

## 目录规划

```text
apps/
  card-web/       # 通用访客 H5、tenant 解析和企业内容包
  admin-web/      # 企业内容、知识、发布和名片主人后台
services/
  api/            # FastAPI 模块化业务 API
  embedding/      # 本地 OpenAI-compatible 多语种向量服务
  worker/         # 索引、摘要、通知、评测任务
packages/
  contracts/      # OpenAPI、内容 Schema、事件和共享枚举
services/api/migrations/
                  # PostgreSQL/pgvector Alembic 迁移
infra/            # 本地与部署基础设施
docs/             # 开发基线、内容底稿与决策记录
tools/            # 文档和工程辅助工具
```
