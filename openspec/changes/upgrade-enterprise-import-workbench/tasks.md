## WP1 Shared contract and persistence

冻结批次命名、候选批量接受、发布影响/修订/回退合同；增加迁移、模型、schemas 和 focused API tests。依赖：无。验证：migration head、ruff、pytest、OpenAPI check。

## WP2 Import workbench API

实现企业内编号、默认命名、重命名、批次详情/历史摘要、批量接受与待处理计数；保留现有解析/Worker。依赖：WP1。

## WP3 Import workbench UI

新增路由/导航/页面；四个内容页增加统一入口；把现有导入组件拆成上传、批次导航和候选审核工作区。桌面单条审核，移动端逐层导航。依赖：WP1/WP2。

## WP4 Versioned publication impact

为产品、案例、FAQ 实现影响预览、确认发布、修订历史和回退；关联名片集合变化必须 409。依赖：WP1。

## WP5 Website-only verification

启动当前服务，从网站登录开始完整跑通上传、命名、分类审核、发布、名片更新和回退；明确缺陷直接修复，不确定项写 discussion log。依赖：WP2–WP4。
