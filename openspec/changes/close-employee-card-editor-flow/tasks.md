## Work Packages

### WP1: Member-source contract

- Files: member schemas/store/routes, admin types/member API, member navigation/page.
- AC: 管理员能以企业员工姓名、职位、头像、业务摘要及受保护联系方式选择有效员工；界面不再使用“企业用户”。
- Verify: member-store and route tests cover same-company, disabled employee and private-field contract.

### WP2: Employee-card ownership and visibility contract

- Files: catalog schemas/store, public projection and API contract, API tests.
- AC: 管理员新建必须选择有效员工；同一员工不能再次新建员工卡；公开联系方式只显示名片明确开放的员工字段。
- Verify: success, duplicate, invalid/disabled owner and mobile/email visibility tests.

### WP3: Creation and editing UX

- Files: CardEditor, CardsPage, focused UI tests and styles only where needed.
- AC: 不再出现手填用户 ID；新建流先选择员工再选择内容起点；编辑界面将身份与名片专属信息分区。
- Verify: component tests and real browser create/edit/reload behavior.

### WP4: Contract and regression proof

- Files: generated OpenAPI contract and current change run evidence only.
- AC: API contract同步；前后端构建、相关测试和 390px/desktop 浏览器流程通过。
- Verify: targeted pytest, admin tests/build, card-web tests/build, OpenAPI check and browser smoke.
