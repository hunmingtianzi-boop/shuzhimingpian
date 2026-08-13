# Implementation Plan

Change: `upgrade-enterprise-import-workbench`

- [x] 1. 冻结并测试批次编号/名称、批量接受和内容发布影响合同；创建 additive migration 和 API schemas。（AC2/AC4/AC5）
- [x] 2. 实现批次默认命名、企业内编号、重命名、历史摘要及高置信候选批量接受。（AC2/AC4/AC7）
- [x] 3. 新增资料导入路由、导航和四个内容页入口；移除 FAQ 页永久展开的导入长区块。（AC1）
- [x] 4. 重构候选审核为任务/候选/详情工作区，补齐响应式、键盘焦点和固定动作。（AC3/AC7）
- [x] 5. 实现产品、案例、FAQ 的关联名片影响预览、确认发布、修订历史和一键回退。（AC5/AC6）
- [x] 6. 同步 OpenAPI，运行 focused API/Admin tests、typecheck/build 和 diff/security review。（AC1–AC7）
- [x] 7. 仅通过网站完成端到端验证并保存关键截图；直接修复确定缺陷，记录需讨论项。（AC8）

## Rollback

UI 路由可隐藏而不影响旧 `/knowledge`；新字段/表为 additive，不删除现有数据。发布修订失败时保留当前已发布内容和旧 API 路径。禁止回滚迁移时删除生产数据。
