## Acceptance Criteria

1. 管理端所有可见入口显示“企业员工”，成员字段可作为员工名片的身份来源。
2. 企业管理员创建员工名片时必须从有效企业员工中选择；没有选择、跨企业、已停用或已有员工名片时服务端安全拒绝。
3. 员工名片编辑器不提供姓名、职位、头像和手填用户 ID 的重复编辑入口；可明确控制企业员工手机和邮箱是否公开。
4. 公开端只返回被允许公开且仍有值的员工联系方式；旧卡兼容不产生意外空白公开页。
5. 默认配置只作为以后新建名片的起点，既有名片不发生隐式改写。

## Evidence

- Focused API tests cover success and denial paths.
- Admin UI tests cover employee selection and identity/visibility presentation.
- Builds and OpenAPI checks pass.
- Browser evidence covers employee selection -> immediate editor -> save -> reload -> public projection.
