# Eval Contract

## Hard Gates

| Gate | Evidence |
| --- | --- |
| 已发布模板不再隐藏原内容目录 | card-web 单测 + 390px 真实浏览器中 7 个固定目录项 |
| 已发布模板不再隐藏原固定业务模块 | card-web 单测 + 浏览器可见企业介绍、核心业务、案例/资料、问答与 AI 路径 |
| 编辑器预览继承原移动端名片外壳 | admin 组件测试 + 桌面和 390px 截图，不存在独立皇家蓝渐变头图 |
| 固定模块与自由模块关系清楚 | 浏览器可见分组目录；固定模块不可删除；自由模块仍可增删排序 |
| 保存、预览、发布、媒体、案例和员工身份契约无回退 | 现有 admin/card 测试与生产构建 |
| 无横向溢出、无阻断性 console 错误 | 1440px 编辑态和 390px 公开端浏览器检查 |

## Commands

- `corepack pnpm --filter admin-web test -- --run`
- `corepack pnpm --filter admin-web build`
- `corepack pnpm --filter card-web test -- --run`
- `corepack pnpm --filter card-web build`
- Playwright runtime smoke on `38181/cards` and `38180/c/tuotu` at desktop and 390px widths.

## Visual rubric

- Structure preservation: 30%
- Mobile-card visual inheritance: 30%
- Editor hierarchy and clarity: 20%
- Responsive behavior: 10%
- Interaction completeness: 10%

## Stop Rule

Do not claim completion while any hard gate fails, while the editor introduces a second visible card style, or while published templates replace rather than extend the original mobile card.
