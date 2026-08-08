import { expect, test, type Page, type Route } from "@playwright/test";

const API = "http://127.0.0.1:8000/api/v1";
const IDS = {
  card: "11111111-1111-4111-8111-111111111111",
  company: "22222222-2222-4222-8222-222222222222",
  visit: "33333333-3333-4333-8333-333333333333",
  visitor: "44444444-4444-4444-8444-444444444444",
  conversation: "55555555-5555-4555-8555-555555555555",
  message: "66666666-6666-4666-8666-666666666666",
  lead: "77777777-7777-4777-8777-777777777777",
};

function cors(route: Route) {
  const origin = route.request().headers().origin ?? "http://127.0.0.1:4173";
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers":
      "Authorization,Content-Type,Idempotency-Key,If-Match,X-CSRF-Token,X-Request-Id",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
    "Access-Control-Expose-Headers": "ETag,X-CSRF-Token,X-Request-Id,Retry-After",
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    headers: cors(route),
    contentType: "application/json; charset=utf-8",
    body: JSON.stringify(body),
  });
}

async function handlePreflight(route: Route) {
  if (route.request().method() !== "OPTIONS") return false;
  await route.fulfill({ status: 204, headers: cors(route), body: "" });
  return true;
}

function publicCard() {
  return {
    id: IDS.card,
    slug: "tuotu",
    display_name: "拓浙 AI 集团",
    title: "拓浙 AI 集团数智名片",
    contact_fields: [{ label: "官网", value: "tuotuzju.com", href: "https://tuotuzju.com" }],
    company: {
      id: IDS.company,
      name: "拓浙 AI 集团",
      summary: "面向企业提供可信的数智化业务协同服务。",
    },
    featured_products: [],
    featured_cases: [],
    faq_items: [],
    ai_assistant: {
      available: true,
      display_name: "拓浙 AI 集团资料助手",
      disclosure: "回答由 AI 基于企业已发布资料生成",
      welcome_message: "你好，我会基于企业已审核资料回答。",
      suggested_questions: ["你们提供什么服务？"],
    },
    policy_versions: {
      privacy: "privacy-2026.07-v1",
      chat_notice: "chat-notice-2026.07-v1",
      lead_consent: "lead-consent-2026.07-v1",
      profile_personalization: "profile-personalization-2026.07-v1",
    },
  };
}

async function mockVisitorApi(page: Page) {
  const unhandled: string[] = [];
  await page.route(`${API}/**`, async (route) => {
    if (await handlePreflight(route)) return;
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const method = request.method();
    if (method === "GET" && path === "/public/cards/tuotu") {
      return json(route, { data: publicCard() });
    }
    if (method === "GET" && path === "/public/cards/tuotu/products") {
      return json(route, {
        data: [
          {
            slug: "digital-card",
            name: "数智名片平台",
            category: "企业服务",
            summary: "企业展示、AI 接待与线索闭环。",
            detail: "基于审核知识回答，并沉淀访问、对话与线索。",
            audience: "需要数字化获客的企业",
            price_boundary: "按实施范围评估",
            sort_order: 1,
            published_at: "2026-07-11T00:00:00Z",
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      });
    }
    if (method === "GET" && path === "/public/cards/tuotu/case-studies") {
      return json(route, { data: [], total: 0, limit: 50, offset: 0 });
    }
    if (method === "GET" && path === "/public/cards/tuotu/recommendations") {
      return json(route, { data: [] });
    }
    if (method === "GET" && path === "/public/cards/tuotu/products/digital-card") {
      return json(route, {
        data: {
          slug: "digital-card",
          name: "数智名片平台",
          category: "企业服务",
          summary: "企业展示、AI 接待与线索闭环。",
          detail: "基于审核知识回答，并沉淀访问、对话与线索。",
          audience: "需要数字化获客的企业",
          price_boundary: "按实施范围评估",
          sort_order: 1,
          published_at: "2026-07-11T00:00:00Z",
        },
      });
    }
    if (method === "POST" && path === "/public/cards/tuotu/visits") {
      return json(route, {
        data: {
          visit_id: IDS.visit,
          visitor_id: IDS.visitor,
          visitor_session_token: "e2e-visitor-token",
          expires_at: "2026-07-11T10:00:00Z",
        },
      }, 201);
    }
    if (method === "POST" && path === "/public/cards/tuotu/consents") {
      return json(route, { data: { id: "consent-e2e", granted: true } }, 201);
    }
    if (method === "POST" && path === "/public/cards/tuotu/conversations") {
      return json(route, { data: { id: IDS.conversation } }, 201);
    }
    if (
      method === "POST" &&
      path === `/public/conversations/${IDS.conversation}/messages:stream`
    ) {
      const stream = [
        `event: message.started\ndata: ${JSON.stringify({ message_id: IDS.message, request_id: "e2e-request" })}\n\n`,
        `event: message.delta\ndata: ${JSON.stringify({ text: "数智名片平台提供企业展示、AI 接待与线索闭环。" })}\n\n`,
        `event: message.citation\ndata: ${JSON.stringify({ citation_id: "citation-1", label: "产品说明", source_type: "product" })}\n\n`,
        `event: message.completed\ndata: ${JSON.stringify({ message_id: IDS.message, finish_reason: "stop", lead_prompt: false })}\n\n`,
      ].join("");
      return route.fulfill({
        status: 200,
        headers: { ...cors(route), "Content-Type": "text/event-stream" },
        body: stream,
      });
    }
    if (method === "POST" && path === "/public/cards/tuotu/leads") {
      return json(route, {
        data: {
          id: IDS.lead,
          status: "new",
          created_at: "2026-07-11T02:00:00Z",
        },
      }, 201);
    }
    unhandled.push(`${method} ${path}`);
    return json(route, { error: { code: "E2E_UNHANDLED", message: "未处理的 E2E 请求" } }, 500);
  });
  return unhandled;
}

test("visitor browses published content, receives a cited AI answer and submits consented lead", async ({
  page,
}) => {
  const unhandled = await mockVisitorApi(page);
  await page.goto("http://127.0.0.1:4173/c/tuotu");

  await expect(page.getByText("拓浙 AI 集团", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "业务", exact: true }).click();
  await expect(page).toHaveURL(/[?&]view=square(?:&|$)/);
  const product = page.getByRole("button", { name: /数智名片平台/ });
  await expect(product).toBeVisible();
  await product.click();
  await expect(page.getByRole("heading", { name: "数智名片平台" })).toBeVisible();
  await expect(page.getByText("基于审核知识回答，并沉淀访问、对话与线索。")).toBeVisible();

  await page.getByRole("button", { name: "向 AI 继续提问", exact: true }).click();
  const question = page.getByPlaceholder("问业务、人才、赛事或合作");
  await question.fill("数智名片平台能做什么？");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect(page.getByText(/企业展示、AI 接待与线索闭环/).last()).toBeVisible();
  await expect(page.getByText("产品说明")).toBeVisible();
  await page.getByRole("button", { name: "关闭助手" }).click();

  await page.getByRole("button", { name: "留下合作需求", exact: true }).click();
  const leadDialog = page.getByRole("dialog", { name: "留下合作需求" });
  await leadDialog.getByLabel("姓名 *").fill("张三");
  await leadDialog.getByRole("textbox", { name: "手机", exact: true }).fill("13800138000");
  await leadDialog.getByLabel("合作需求 *").fill("希望预约数智名片产品演示。");
  await leadDialog
    .locator("label")
    .filter({ hasText: "我同意企业为联系和跟进本次需求" })
    .click();
  await expect(leadDialog.getByRole("checkbox")).toBeChecked();
  await leadDialog.getByRole("button", { name: "确认授权并提交" }).click();
  await expect(page.getByText("需求已安全提交")).toBeVisible();
  await expect(page.getByText(new RegExp(IDS.lead))).toBeVisible();
  expect(unhandled).toEqual([]);
});

async function mockAdminApi(page: Page) {
  const unhandled: string[] = [];
  const enterprises = [
    {
      tenant_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      tenant_slug: "existing",
      tenant_name: "现有租户",
      company_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      company_name: "现有企业",
      status: "active",
      created_at: "2026-07-10T00:00:00Z",
    },
  ];
  let createBody: Record<string, unknown> | undefined;
  await page.route(`${API}/**`, async (route) => {
    if (await handlePreflight(route)) return;
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const method = request.method();
    if (method === "POST" && path === "/auth/login") {
      return json(route, {
        data: { access_token: "e2e-access-token", csrf_token: "e2e-csrf-token" },
      });
    }
    if (method === "GET" && path === "/auth/me") {
      return json(route, {
        data: {
          user: {
            id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            display_name: "平台管理员",
          },
          membership: {
            id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            tenant_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            company_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            role: "platform_admin",
            permissions: ["*"],
          },
        },
      });
    }
    if (method === "GET" && path === "/platform/overview") {
      return json(route, {
        data: {
          generated_at: "2026-07-11T00:00:00Z",
          enterprise_count: 1,
          active_enterprise_count: 1,
          onboarding_count: 0,
          published_card_count: 1,
          visits_30d: 0,
          conversations_30d: 0,
          leads_30d: 0,
          failed_task_count: 0,
          llm_ready: true,
          import_ready: true,
        },
      });
    }
    if (method === "GET" && path === "/platform/enterprises") {
      return json(route, { data: enterprises, total: enterprises.length, limit: 50, offset: 0 });
    }
    if (method === "POST" && path === "/platform/enterprises") {
      createBody = request.postDataJSON() as Record<string, unknown>;
      const created = {
        tenant_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        tenant_slug: String(createBody.tenant_slug),
        tenant_name: String(createBody.tenant_name),
        company_id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
        company_name: String(createBody.company_name),
        company_status: "active",
        admin_user_id: "12121212-1212-4212-8212-121212121212",
        admin_membership_id: "13131313-1313-4313-8313-131313131313",
        initial_card_id: "14141414-1414-4414-8414-141414141414",
        initial_card_slug: "c-e2e-random-slug",
        created_at: "2026-07-11T03:00:00Z",
      };
      enterprises.push({ ...created, status: "active" });
      return json(route, { data: created }, 201);
    }
    unhandled.push(`${method} ${path}`);
    return json(route, { error: { code: "E2E_UNHANDLED", message: "未处理的 E2E 请求" } }, 500);
  });
  return { unhandled, createBody: () => createBody };
}

test("platform administrator signs in and creates an isolated enterprise", async ({ page }) => {
  const mock = await mockAdminApi(page);
  await page.goto("http://127.0.0.1:4174/");

  await page.getByLabel("账号").fill("platform@example.test");
  await page.getByLabel("密码").fill("Local-Platform-Password-2026!");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "平台运营中心" })).toBeVisible();
  await page.getByRole("link", { name: "企业管理" }).click();
  await expect(page.getByRole("heading", { name: "企业中心" })).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "平台企业列表" })
      .getByRole("cell", { name: "现有企业", exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "直接开通空白企业" }).click();
  await page.getByLabel("租户标识").fill("new-enterprise");
  await page.getByLabel("租户名称").fill("新企业租户");
  await page.getByLabel("企业名称").fill("新企业有限公司");
  await page.getByLabel("行业").fill("企业服务");
  await page.getByLabel("管理员账号").fill("admin@new-enterprise.test");
  await page.getByLabel("管理员姓名").fill("新企业管理员");
  await page.getByLabel("初始密码").fill("Initial-Enterprise-Password-2026!");
  await page.getByLabel("初始名片标题").fill("新企业数智名片");
  await page.getByRole("button", { name: "确认开通" }).click();

  await expect(page.getByText(/企业 新企业有限公司 已开通/)).toBeVisible();
  expect(mock.createBody()).toMatchObject({
    tenant_slug: "new-enterprise",
    admin_account: "admin@new-enterprise.test",
    admin_password: "Initial-Enterprise-Password-2026!",
  });
  await expect(page.locator("body")).not.toContainText("Initial-Enterprise-Password-2026!");
  expect(mock.unhandled).toEqual([]);
});
