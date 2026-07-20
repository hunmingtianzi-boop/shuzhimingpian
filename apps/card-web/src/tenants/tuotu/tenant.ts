import type { KnowledgeItem } from "../../domain/card";
import { defineTenant } from "../defineTenant";

const assetBase = import.meta.env.BASE_URL.replace(/\/?$/, "/");
const asset = (fileName: string) => `${assetBase}tenants/tuotu/assets/${fileName}`;

const sourceDate = "2026 年 7 月";
const sourceOverview = "《拓浙 AI 生态内部总纲》v0.1；《业务梳理讨论智能纪要》P1-P3（2026-07）";
const sourceModel = "《拓浙 AI 生态内部总纲》〇、七；《IPO 整合版》2.1-2.6（2026-07）";

const knowledgeBase: KnowledgeItem[] = [
  {
    id: "overview",
    question: "拓浙 AI 集团主要做什么？",
    shortQuestion: "集团主要做什么？",
    answer:
      `**核心定位：** 拓浙 AI 集团围绕 **AI 人才与项目孵化**、**AI 场景服务** 两大方向展开。

- **连接对象：** 青年人才、学习与项目组织、创新赛事和产业伙伴。
- **目标：** 让真实问题同时成为人才成长与应用验证的起点。`,
    keywords: ["拓浙", "集团", "主要", "做什么", "定位", "介绍", "生态", "业务"],
    source: sourceOverview,
  },
  {
    id: "businesses",
    question: "拓浙 AI 集团有哪些业务板块？",
    shortQuestion: "有哪些业务板块？",
    answer:
      `**公开业务板块：** 目前由 **4 个协同板块** 组成。

- **拓途浙享：** 提供活动、内容与项目入口。
- **智能体学习与项目社群：** 承接训练、组队和实践。
- **浙客松：** 用于真实场景下的创新验证与成果展示。
- **AI 场景服务：** 围绕需求诊断、原型验证、定制开发和持续迭代推进产业共创。`,
    keywords: ["业务", "板块", "产品", "架构", "拓途浙享", "社群", "浙客松", "场景服务"],
    source: sourceModel,
  },
  {
    id: "platform",
    question: "拓途浙享平台有什么作用？",
    shortQuestion: "拓途浙享做什么？",
    answer:
      `**平台定位：** 拓途浙享是生态的线上入口。

- **当前连接：** 聚合校园活动与 AI 学习内容，并连接项目、组队和成果展示。
- **开放边界：** 部分项目广场与成果沉淀能力仍属于规划方向，具体开放状态以平台页面为准。`,
    keywords: ["拓途浙享", "网站", "平台", "活动", "内容", "项目", "组队", "成果"],
    source: "《拓浙 AI 生态内部总纲》一、七；《拓浙 AI 生态规划书》平台章节（2026-07）",
  },
  {
    id: "talent",
    question: "学生可以如何加入并获得成长？",
    shortQuestion: "学生如何加入？",
    answer:
      `**加入路径：** 不同基础的学生都可以先从公开内容、主题工作坊和基础训练开始。

1. **入门学习：** 从公开内容、主题工作坊或基础训练进入。
2. **实践积累：** 通过组队、真实项目或浙客松沉淀作品。
3. **进一步参与：** 有技术基础的参与者可承担项目任务。

具体招募、课程、认证和人才机会以当期正式通知为准。`,
    keywords: ["学生", "加入", "报名", "零基础", "新手", "学习", "训练", "成长", "项目"],
    source: "《拓浙 AI 生态内部总纲》一至四；《IPO 整合版》2.2-2.4（2026-07）",
  },
  {
    id: "hackathon",
    question: "浙客松是什么？",
    shortQuestion: "介绍一下浙客松",
    answer:
      `**浙客松：** 面向真实场景的 AI 创新赛事与项目验证活动。

- **活动方式：** 通过跨学科组队、阶段性评审和成果展示，观察人才能力与项目潜力。
- **阶段数据：** 材料记录首届约 **300 人报名**、**100 人正式参赛**。
- **规则边界：** 具体赛题、证明与后续权益以当期规则为准。`,
    keywords: ["浙客松", "黑客松", "赛事", "比赛", "赛题", "报名", "参赛", "成果"],
    source: "《拓浙 AI 生态内部总纲》五、十；《拓浙 AI 生态规划书》浙客松章节（2026-07）",
  },
  {
    id: "service",
    question: "AI 场景服务包括哪些内容？",
    shortQuestion: "AI 场景服务做什么？",
    answer:
      `**服务范围：** AI 场景服务从具体业务问题出发，形成从诊断到迭代的协作链路。

- **前期：** 需求梳理、场景评估和方案设计。
- **实施：** 原型验证、定制开发和数据资产整理。
- **持续阶段：** 根据实际效果持续迭代。

项目目标、周期与验收指标需结合业务范围、数据条件和合规要求单独约定，**不使用统一准确率或效果承诺**。`,
    keywords: ["AI 场景", "定制化", "服务", "开发", "原型", "数据", "方案", "迭代", "效果"],
    source: "《业务梳理讨论智能纪要》P2；《IPO 整合版》2.5（2026-07）",
  },
  {
    id: "cooperation",
    question: "企业可以怎样与拓浙 AI 集团合作？",
    shortQuestion: "企业如何合作？",
    answer:
      `**合作方式：** 企业可提交 AI 应用场景、联合发布真实赛题、共建项目实践，或开展青年人才交流。

\`\`\`mermaid
flowchart TD
  A[需求沟通] --> B[场景评估]
  B --> C[范围确认]
  C --> D[团队匹配]
  D --> E[阶段验证]
  E --> F[成果复盘]
\`\`\`

> **项目约定：** 费用、周期、数据使用、知识产权、保密与验收方式需按项目另行确认。`,
    keywords: ["企业", "合作", "商务", "共建", "赛题", "项目", "人才", "知识产权", "保密"],
    source: "《拓浙 AI 生态内部总纲》六、九；《业务梳理讨论智能纪要》P2-P3（2026-07）",
  },
  {
    id: "metrics",
    question: "目前有哪些可以展示的阶段数据？",
    shortQuestion: "目前规模如何？",
    answer:
      `**阶段数据：** 以下为 **2026 年 7 月内部材料** 记录。

| 指标 | 记录 |
| --- | --- |
| 平台注册用户 | **2300+** |
| 累计收录校园活动 | **700+** |
| 首届浙客松报名 | 约 **300 人** |
| 正式参赛 | 约 **100 人** |

> 以上不是实时接口数据，正式发布前仍需复核统计截止日期和统计方式。`,
    keywords: ["规模", "数据", "用户", "活动", "多少人", "报名", "参赛", "2300", "700"],
    source: "《拓浙 AI 生态内部总纲》十；《拓浙 AI 生态规划书》数据页（2026-07）",
  },
  {
    id: "official",
    question: "这是浙江大学官方项目或官方平台吗？",
    shortQuestion: "这是浙大官方项目吗？",
    answer:
      `**结论：** 现有材料不足以证明这是 **浙江大学官方主体项目** 或已获得统一授权。

- **已知背景：** 项目从浙江大学校园场景出发，并讨论产学协同与相关校内资源。
- **公开边界：** 合作称谓和标识使用应以集团及相关单位最终确认的文件为准。`,
    keywords: ["浙江大学", "浙大", "官方", "学校", "隶属", "授权", "背书", "校内"],
    source: "《拓浙 AI 生态规划书》；《拓浙 AI 生态内部总纲》九、十二（2026-07）",
  },
  {
    id: "opportunity",
    question: "参加项目是否保证认证、实习或就业机会？",
    shortQuestion: "会保证实习就业吗？",
    answer:
      `**结论：** **不保证** 认证、实习或就业结果。

- **可能提供：** 成果评价、证明或交流机会。
- **以规则为准：** 具体认证名称、适用范围和人才权益以对应活动及合作方正式规则为准。
- **不作承诺：** 不作内推、录用、投资或孵化结果承诺。`,
    keywords: ["保证", "认证", "证书", "实习", "内推", "就业", "录用", "投资", "孵化"],
    source: "《拓浙 AI 生态内部总纲》九、十二；公开承诺边界（2026-07）",
  },
  {
    id: "contact",
    question: "如何联系或加入拓浙 AI 集团？",
    shortQuestion: "怎么联系或加入？",
    answer:
      `**建议入口：** 可先访问 **tuotuzju.com** 查看公开内容、活动与报名入口。

- **当前资料边界：** 尚未提供经确认可公开的集团电话、邮箱、微信、联系人或统一入群入口。
- **后续要求：** 正式上线前需由集团补齐官方商务与加入渠道。`,
    keywords: ["联系", "加入", "电话", "邮箱", "微信", "入群", "地址", "入口"],
    source: "资料联系人盘点；拓途浙享公开入口（2026-07）",
  },
];

export const tuotuTenant = defineTenant({
  id: "tuotu",
  version: "2026.07-v0.2.3",
  seo: {
    title: "拓浙 AI 集团 | 青年 AI 人才与产业场景共创",
    description:
      "拓浙 AI 集团数智名片，介绍拓途浙享、人才成长、浙客松与 AI 场景服务。",
  },
  brand: {
    name: "拓浙 AI 集团",
    shortName: "拓浙 AI",
    tagline: "青年 AI 人才与产业场景共创生态",
    headerDescriptor: "人才 · 项目 · 产业场景",
    logo: {
      src: asset("tuotu-logo.webp"),
      alt: "拓浙 AI 集团品牌标识",
      width: 191,
      height: 192,
    },
    homeAriaLabel: "返回拓浙 AI 集团首页",
    officialAction: {
      kind: "external",
      label: "进入平台",
      target: "https://tuotuzju.com",
    },
  },
  theme: {
    defaultMode: "system",
    action: "#64e3f6",
    onAction: "#041014",
    light: {
      accent: "#006f84",
      accentStrong: "#005f72",
      accentSoft: "rgba(8, 155, 181, 0.12)",
      background: "#f1f4f5",
      surface: "#fbfcfc",
      surfaceRaised: "#f6f9fa",
      surfaceMuted: "#e8edef",
      text: "#0a1720",
      textSoft: "#54636b",
      textFaint: "#5b6a72",
      line: "rgba(10, 23, 32, 0.13)",
      lineStrong: "rgba(10, 23, 32, 0.22)",
      shadow: "0 28px 80px rgba(24, 43, 53, 0.12)",
    },
    dark: {
      accent: "#48d7ee",
      accentStrong: "#8be8f6",
      accentSoft: "rgba(72, 215, 238, 0.12)",
      background: "#071017",
      surface: "#0d1921",
      surfaceRaised: "#12212a",
      surfaceMuted: "#172730",
      text: "#f4f8fa",
      textSoft: "#a7b5bc",
      textFaint: "#7d8d96",
      line: "rgba(211, 236, 242, 0.14)",
      lineStrong: "rgba(211, 236, 242, 0.24)",
      shadow: "0 28px 90px rgba(0, 0, 0, 0.34)",
    },
    heroOverlay: {
      light: "rgba(238, 243, 245, 0.14)",
      dark: "rgba(2, 10, 17, 0.28)",
    },
    radiusCard: "24px",
    radiusControl: "999px",
    radiusSmall: "12px",
  },
  hero: {
    id: "top",
    kicker: "拓浙 AI 集团 · 数智名片",
    titleLines: ["让真实问题", "成为成长现场"],
    summary:
      "连接青年 AI 人才、高校创新资源与产业场景，通过学习社区、项目实战、浙客松与 AI 场景服务，推动人才成长和应用落地。",
    art: {
      src: asset("hero-ecosystem.webp"),
      alt: "",
      width: 1717,
      height: 916,
    },
    actions: [
      { kind: "anchor", label: "了解业务", target: "#ecosystem" },
      { kind: "anchor", label: "发起合作", target: "#cooperation" },
    ],
    metrics: [
      { value: "2300+", label: "平台注册用户", note: "截至 2026.07" },
      { value: "700+", label: "校园活动收录", note: "截至 2026.07" },
      { value: "约 300", label: "首届浙客松报名", note: "内部资料口径" },
      { value: "100", label: "正式参赛", note: "内部资料口径" },
    ],
  },
  sections: [
    {
      type: "feature-grid",
      id: "ecosystem",
      navLabel: "业务",
      showInNav: true,
      eyebrow: "四个协同板块",
      heading: "从人才成长到产业共创，四个板块彼此接力",
      description:
        "平台提供入口，社群组织成长，赛事完成创新验证，场景服务把真实需求带进项目实践。",
      businesses: [
        {
          icon: "globe",
          eyebrow: "平台入口",
          title: "拓途浙享",
          description: "聚合校园活动与 AI 内容，连接项目、团队和成果展示。",
          status: "持续沉淀公开内容",
          points: ["校园活动聚合", "AI 学习内容", "项目与组队入口", "成果展示"],
        },
        {
          icon: "path",
          eyebrow: "人才成长",
          title: "智能体学习与项目社群",
          description: "通过入门训练、主题工作坊和真实项目，帮助不同基础的学生进入 AI 实践。",
          status: "按不同基础进入实践",
          points: ["入门训练", "跨学科组队", "真实项目", "作品复盘"],
        },
        {
          icon: "rocket",
          eyebrow: "创新验证",
          title: "浙客松",
          description: "围绕真实场景开展跨学科共创，在短周期内验证能力、创意与项目潜力。",
          status: "具体赛题以当期规则为准",
          points: ["真实场景命题", "跨学科协作", "阶段性评审", "成果展示"],
        },
        {
          icon: "buildings",
          eyebrow: "产业共创",
          title: "AI 场景服务",
          description: "从业务需求梳理出发，推进原型验证、定制开发和持续迭代。",
          status: "按项目评估服务范围",
          points: ["场景诊断", "原型验证", "定制开发", "持续迭代"],
        },
      ],
    },
    {
      type: "media-showcase",
      id: "platform",
      navLabel: "平台",
      showInNav: true,
      eyebrow: "拓途浙享",
      heading: "先让机会被看见，再让参与发生",
      description:
        "拓途浙享以校园活动和公开内容作为入口，逐步连接 AI 学习、团队协作、项目实践与成果沉淀。",
      capabilities: [
        {
          icon: "calendar",
          title: "活动聚合",
          description: "汇集讲座、竞赛、志愿、招新等校园机会",
        },
        {
          icon: "book",
          title: "学习内容",
          description: "沉淀教程、工具、技术文章与实践经验",
        },
        {
          icon: "code",
          title: "项目连接",
          description: "连接组队、真实需求、过程记录与成果展示",
        },
      ],
      action: {
        kind: "external",
        label: "进入拓途浙享",
        target: "https://tuotuzju.com",
      },
      visualLabel: "平台界面资料",
      visualTitle: "校园活动聚合入口",
      visual: {
        src: asset("platform-events.webp"),
        alt: "拓途浙享活动聚合界面，包含活动分类、学院筛选和活动卡片",
        caption: "资料内嵌产品界面；具体功能与开放状态以当前平台为准。",
        width: 2048,
        height: 1043,
      },
    },
    {
      type: "process",
      id: "journey",
      navLabel: "路径",
      showInNav: true,
      eyebrow: "双轴生态 · 公开简版",
      heading: "一条共同起点，两种成长出口",
      description:
        "访客从发现机会、学习和实战进入生态；真实项目之后，既可以走向人才发展，也可以继续推动项目成长。",
      steps: [
        {
          title: "发现机会",
          text: "从活动、公开内容、社群或赛事找到适合自己的入口。",
          path: "shared",
        },
        {
          title: "学习成长",
          text: "按基础进入工具、编程、智能体或主题工作坊。",
          path: "shared",
        },
        {
          title: "参与实战",
          text: "通过真实项目或浙客松完成组队、协作与成果验证。",
          path: "shared",
        },
        {
          title: "人才发展",
          text: "沉淀作品与合作方评价，连接后续项目和人才交流机会。",
          path: "branch-a",
        },
        {
          title: "项目成长",
          text: "通过展示、复盘和资源对接，继续推进验证与共创。",
          path: "branch-b",
        },
      ],
      audienceHeading: "四个板块，在同一条链路上接力",
      audiences: [
        {
          icon: "globe",
          title: "拓途浙享",
          description: "在发现、学习与成果沉淀阶段提供线上入口。",
        },
        {
          icon: "path",
          title: "学习与项目社群",
          description: "承接训练、组队、项目协作与复盘。",
        },
        {
          icon: "rocket",
          title: "浙客松",
          description: "把真实挑战转化为短周期创新验证场。",
        },
        {
          icon: "buildings",
          title: "AI 场景服务",
          description: "从产业需求出发，推进评估、研发与迭代。",
        },
      ],
    },
    {
      type: "evidence",
      id: "hackathon",
      navLabel: "浙客松",
      showInNav: true,
      eyebrow: "创新验证",
      heading: "让一场赛事，成为能力与项目的共同试验场",
      description:
        "浙客松用真实问题组织跨学科共创，把学习、组队、评审和成果展示压缩进一条可观察的实践链路。",
      visual: {
        src: asset("hackathon-group.webp"),
        alt: "AI 全栈极速黑客松活动现场合影，参与者在会场屏幕前合照",
        caption: "资料图片；公开发布前需确认活动图片与人物肖像授权。",
        width: 1379,
        height: 744,
      },
      headlineMetric: "约 300 / 100",
      metricDescription: "内部材料记录：首届约 300 人报名、100 人正式参赛",
      themesAriaLabel: "材料涉及的场景方向",
      themes: ["教育科技", "医疗健康", "文化旅游", "企业服务", "智能硬件", "数据与效率"],
      caveat:
        "场景方向用于说明生态覆盖面，不等同于已落地项目；具体赛题、证明与人才权益以当期规则为准。",
      supportHeading: "从真实问题到可见成果",
      supportNote: "公开版只保留方法，不展示未授权合作名单",
      supportNames: ["真实场景命题", "跨学科组队", "阶段性评审", "成果展示"],
    },
    {
      type: "engagement",
      id: "cooperation",
      navLabel: "合作",
      showInNav: true,
      eyebrow: "产业共创",
      heading: "把真实需求，变成下一次共创",
      description:
        "无论是 AI 场景验证、联合赛题、项目共建还是青年人才合作，都从一个明确的问题和边界开始。",
      steps: [
        {
          title: "场景沟通",
          text: "说明业务目标、使用对象、数据条件与合规边界。",
        },
        {
          title: "范围确认",
          text: "共同确定方案、交付物、周期、分工与验收方式。",
        },
        {
          title: "联合验证",
          text: "匹配团队，完成原型、开发、测试和阶段复盘。",
        },
        {
          title: "持续迭代",
          text: "根据验证结果决定优化、扩展或后续人才合作。",
        },
      ],
      cta: {
        title: "从一个具体问题开始",
        description: "可咨询 AI 场景服务、联合赛题、项目共建与青年人才合作。",
        action: {
          kind: "assistant",
          label: "了解合作方式",
          target: "企业可以怎样与拓浙 AI 集团合作？",
        },
      },
    },
    {
      type: "faq",
      id: "faq",
      navLabel: "问答",
      showInNav: true,
      eyebrow: "常见问题",
      heading: "先把业务、合作和边界说明白",
      description:
        "以下回答来自 2026 年 7 月整合材料；未确认的主体关系、合作权益与效果数字不会作为事实输出。",
      itemIds: ["overview", "businesses", "talent", "service", "cooperation", "official"],
      action: {
        kind: "assistant",
        label: "继续向资料助手提问",
        target: "open",
      },
    },
    {
      type: "closing",
      id: "closing",
      navLabel: "收束",
      showInNav: false,
      heading: "让人才在真实问题中成长，让场景在共创中落地",
      description: "了解平台、项目、赛事与合作方式，或向资料助手继续提问。",
      art: {
        src: asset("hero-ecosystem.webp"),
        alt: "",
        width: 1717,
        height: 916,
      },
      actions: [
        { kind: "assistant", label: "问资料助手", target: "open" },
        { kind: "external", label: "进入拓途浙享", target: "https://tuotuzju.com" },
      ],
    },
  ],
  assistant: {
    title: "拓浙 AI 集团资料助手",
    status: "资料版",
    subtitle: "基于 2026 年 7 月整合材料",
    launcherAriaLabel: "打开拓浙 AI 集团资料助手",
    launcherKicker: "资料内回答",
    launcherLabel: "问资料助手",
    initialMessage: {
      text: `**你好，我是拓浙 AI 集团资料助手。**

- 我会根据 **2026 年 7 月整合材料** 回答。
- 我会区分已记录事实、规划方向与待确认事项。`,
      source: `整合知识库 · ${sourceDate}`,
    },
    quickQuestionIds: ["overview", "businesses", "cooperation"],
    labels: {
      closeBackdrop: "关闭资料助手",
      closeButton: "关闭助手",
      quickQuestions: "常见问题",
      quickQuestionsIntro: "可以先问",
      loading: "正在检索资料",
      input: "向资料助手提问",
      placeholder: "问业务、人才、赛事或合作",
      send: "发送问题",
      sourcePrefix: "来源：",
    },
    disclaimer: "回答来自 2026 年 7 月整合材料，不构成实时承诺或合作确认。",
    knowledgeBase,
    fallback: {
      answer:
        `**当前资料暂未覆盖这个问题。** 我不能根据猜测补充。

- **可以尝试：** 换一个问法，或访问 **tuotuzju.com** 查看公开信息。
- **商务问题：** 仍需要由集团提供人工联系入口。`,
      source: "资料边界规则",
    },
  },
  footer: {
    brandNote: "青年 AI 人才与产业场景共创",
    disclaimer:
      "当前为资料整合预览；集团主体、数据口径、合作关系、联系渠道与素材授权以正式发布终审为准。",
    backToTopAction: { kind: "anchor", label: "返回顶部", target: "#top" },
  },
  presentation: {
    homepageContentMode: "curated",
    heroVisual: {
      src: asset("card-ui/enterprise-city-1600.webp"),
      srcSet: `${asset("card-ui/enterprise-city-800.webp")} 800w, ${asset("card-ui/enterprise-city-1600.webp")} 1600w`,
      sizes: "(max-width: 480px) 100vw, 480px",
      alt: "蓝色夜幕下的现代城市与科技园区",
      width: 1600,
      height: 1200,
    },
    heroSummary:
      "连接青年 AI 人才、高校创新资源与产业场景，让学习、项目、赛事与应用落地彼此接力。",
    solutions: [
      {
        id: "talent-incubation",
        title: "AI 人才与项目孵化",
        description: "连接学习、组队与真实项目，让青年人才在实践中形成作品与能力。",
      },
      {
        id: "innovation-event",
        title: "AI 创新赛事",
        description: "以浙客松承接真实场景命题，验证创意、能力与项目潜力。",
      },
      {
        id: "scenario-service",
        title: "AI 场景服务",
        description: "从需求诊断到原型验证和持续迭代，推动应用进入真实业务。",
      },
    ],
    caseStudy: {
      title: "首届浙客松 AI 创新实践",
      category: "创新赛事",
      description:
        "约 300 人报名、100 人正式参赛，通过跨学科组队、阶段评审和成果展示完成真实场景验证。",
      detail:
        "首届浙客松围绕真实问题组织青年人才跨学科协作，在短周期内完成赛题理解、方案构思、原型验证与成果展示。数据来自 2026 年 7 月整合材料，后续活动规则与口径以当期正式通知为准。",
      visual: {
        src: asset("hackathon-group.webp"),
        alt: "首届浙客松参与者集体合影",
        width: 1200,
        height: 900,
      },
    },
    owner: {
      demoLabel: "演示资料，待替换",
      name: "负责人姓名",
      role: "创始人 / 总经理",
      summary:
        "围绕青年 AI 人才成长、项目孵化与产业场景共创，推动多方资源形成持续合作。",
      valueProposition:
        "以长期主义为底色，把真实问题转化为人才成长与项目落地的共同起点。",
      capabilities: ["生态共建", "项目孵化", "产业协同"],
      experiences: [
        {
          period: "20XX - 至今",
          organization: "公司名称 A",
          role: "创始人 / 总经理",
          description: "负责组织战略、生态合作与重点项目推进。",
        },
        {
          period: "20XX - 20XX",
          organization: "公司名称 B",
          role: "联合创始人 / 副总裁",
          description: "负责业务板块建设、资源协同与市场拓展。",
        },
        {
          period: "20XX - 20XX",
          organization: "公司名称 C",
          role: "高级经理",
          description: "参与关键项目交付、流程优化与团队协作。",
        },
      ],
      portrait: {
        src: asset("card-ui/demo-owner-1024.webp"),
        srcSet: `${asset("card-ui/demo-owner-512.webp")} 512w, ${asset("card-ui/demo-owner-1024.webp")} 1024w`,
        sizes: "(max-width: 480px) 44vw, 210px",
        alt: "虚构的演示商务人物形象",
        width: 1024,
        height: 1280,
      },
    },
    assistantVisual: {
      src: asset("card-ui/ai-assistant-1200.webp"),
      srcSet: `${asset("card-ui/ai-assistant-600.webp")} 600w, ${asset("card-ui/ai-assistant-1200.webp")} 1200w`,
      sizes: "(max-width: 480px) 52vw, 250px",
      alt: "蓝白色企业 AI 助手形象",
      width: 1200,
      height: 1200,
    },
    assistantQuestionIds: ["overview", "businesses", "service", "cooperation", "metrics"],
    assistantRecommendations: [
      {
        title: "AI 人才与项目孵化",
        description: "了解青年人才如何进入学习、组队与真实项目。",
        question: "学生可以如何加入并获得成长？",
      },
      {
        title: "浙客松",
        description: "查看真实场景创新赛事的参与方式与阶段数据。",
        question: "浙客松是什么？",
      },
      {
        title: "AI 场景服务",
        description: "了解从需求诊断到原型验证的协作范围。",
        question: "AI 场景服务包括哪些内容？",
      },
    ],
  },
});
