import type { EnterpriseCardConfig } from "../domain/card";
import type { PublicCardData } from "./publicCardApi";

export type MockCardKind = "employee" | "enterprise";

export function resolveMockCardKind(search: string): MockCardKind | undefined {
  const value = new URLSearchParams(search).get("mock-card");
  return value === "employee" || value === "enterprise" ? value : undefined;
}

export function createMockPublicCard(
  tenant: EnterpriseCardConfig,
  kind: MockCardKind,
): PublicCardData {
  const isEmployee = kind === "employee";
  const companyName = isEmployee ? "创非凡 | 世会智联" : tenant.brand.name;
  const employeeAsset = (fileName: string) =>
    `${import.meta.env.BASE_URL}card-assets/xusongbo/${fileName}`;
  return {
    id: `mock-${kind}`,
    slug: tenant.id,
    card_kind: kind,
    display_name: isEmployee ? "徐松波" : companyName,
    title: isEmployee ? "董事长" : "企业官方名片",
    avatar_url: isEmployee ? employeeAsset("avatar.webp") : null,
    business_summary: isEmployee
      ? "长期服务企业数字化与产业协同，聚焦技术生态、商务连接和组织增长。"
      : undefined,
    identity_titles: isEmployee ? [
      "华为 IT 省代、腾讯官方服务商",
      "世界会长大会执行及系统开发单位",
      "浙江省科技创新企业协会副会长",
      "浙江省科创协 AI 科创专委会主任",
      "浙江省办公服务行业协会副会长",
    ] : [],
    identity_positioning: isEmployee ? "总经办" : null,
    identity_tags: isEmployee ? ["产业协同", "企业服务", "生态共建"] : [],
    contact_fields: [
      { label: "联系电话", value: "186 5718 9955", href: "tel:18657189955" },
      { label: "办公地址", value: "杭州余杭区文一西路998号海外高层次人才创新园11号楼四层" },
    ],
    company: {
      id: `mock-company-${tenant.id}`,
      name: companyName,
      summary:
        tenant.hero.summary ||
        "以 AI 数智名片为入口，为企业提供持续在线的商务接待、需求识别与线索沉淀。",
      industry: "人工智能与企业服务",
      region: "浙江杭州",
      website: tenant.brand.officialAction.target,
      logo_url: isEmployee ? employeeAsset("company-logo.webp") : tenant.brand.logo.src,
      official_card_slug: tenant.id,
    },
    featured_products: [
      { title: "企业 AI 商务接待", description: "基于企业公开资料回答业务问题并识别合作意向。" },
      { title: "数智名片", description: "连接个人身份、企业能力与访客需求。" },
    ],
    featured_cases: [
      { title: "商协会企业 AI 接待试点", description: "用统一名片入口承接企业展示、问答与合作需求。", industry: "商协会" },
    ],
    faq_items: [
      {
        id: "mock-faq-1",
        question: "数智名片和普通电子名片有什么区别？",
        answer: "数智名片不仅展示信息，还通过 AI 主动接待、意图识别和拜访纪要延续商务沟通。",
        source_label: "模拟企业公开资料",
      },
    ],
    ai_assistant: {
      available: true,
      display_name: isEmployee ? "徐松波的 AI 助手" : `${companyName} AI 助手`,
      disclosure: "当前为前端模拟；正式回答将基于企业已发布资料并提供必要的人工确认。",
      welcome_message: isEmployee
        ? "您好，我可以先介绍徐松波负责的业务、代表案例和合作方式。"
        : "您好，我可以介绍企业能力、产品服务、公开案例和合作路径。",
      suggested_questions: [
        "你们最适合服务哪类企业？",
        "可以介绍一个代表案例吗？",
        "我想谈合作，下一步怎么做？",
      ],
    },
    enterprise_template: isEmployee ? {
      schema_version: 2,
      theme_key: "executive",
      blocks: [
        {
          id: "executive-identity",
          type: "identity",
          title: "基础名片",
          visible: true,
          show_title: false,
          directory_enabled: false,
          sort_order: 0,
          presentation: {
            identity_layout: "horizontal",
            background: {
              asset_url: employeeAsset("card-background.webp"),
              fit: "cover",
              position: "top",
              opacity: 1,
              overlay: "none",
            },
          },
        },
        {
          id: "executive-entries",
          type: "action_collection",
          title: "业务入口",
          visible: true,
          show_title: false,
          directory_enabled: false,
          sort_order: 10,
          action_template: "quick",
          action_items: [
            { id: "conference", title: "非凡大会", image_url: employeeAsset("nav-conference.webp"), target_type: "internal_path", target_value: "/__wecom/miniprogram?app_id=wxe79dc0e12345620d&path=pages%2Findex%2Findex.html" },
            { id: "events", title: "非凡活动", image_url: employeeAsset("nav-events.webp"), target_type: "internal_path", target_value: "/__wecom/miniprogram?app_id=wxe79dc0e12345620d&path=pages%2Findex%2Fdiy.html%3Fid%3D11" },
            { id: "network", title: "非凡互联", image_url: employeeAsset("nav-network.webp"), target_type: "internal_path", target_value: "/__wecom/miniprogram?app_id=wxe79dc0e12345620d&path=pages%2Findex%2Fdiy.html%3Fid%3D12" },
            { id: "selection", title: "非凡臻选", image_url: employeeAsset("nav-selection.webp"), target_type: "internal_path", target_value: "/__wecom/miniprogram?app_id=wxe79dc0e12345620d&path=pages%2Findex%2Fdiy.html%3Fid%3D13" },
          ],
        },
        {
          id: "executive-image-hero",
          type: "image_gallery",
          title: "品牌展示",
          visible: true,
          show_title: false,
          directory_enabled: false,
          sort_order: 30,
          layout_variant: "list",
          gallery_items: [{ id: "hero", image_url: employeeAsset("brand-hero.webp"), badge_mode: "none", alt_text: "创非凡品牌展示" }],
        },
        {
          id: "executive-image-2",
          type: "image_gallery",
          title: "创非凡介绍",
          visible: true,
          show_title: false,
          directory_enabled: false,
          sort_order: 40,
          layout_variant: "list",
          gallery_items: [{ id: "brand-2", image_url: employeeAsset("brand-cfeifan.webp"), badge_mode: "none", alt_text: "创非凡企业介绍" }],
        },
        {
          id: "executive-image-3",
          type: "image_gallery",
          title: "世会智联介绍",
          visible: true,
          show_title: false,
          directory_enabled: false,
          sort_order: 50,
          layout_variant: "list",
          gallery_items: [{ id: "brand-3", image_url: employeeAsset("brand-shihui.webp"), badge_mode: "none", alt_text: "世会智联介绍" }],
        },
        {
          id: "executive-image-4",
          type: "image_gallery",
          title: "品牌能力",
          visible: true,
          show_title: false,
          directory_enabled: false,
          sort_order: 60,
          layout_variant: "list",
          gallery_items: [{ id: "brand-4", image_url: employeeAsset("brand-capability.webp"), badge_mode: "none", alt_text: "创非凡品牌能力" }],
        },
        {
          id: "executive-dynamics",
          type: "image_gallery",
          title: "创非凡|世会智联动态",
          visible: true,
          show_title: true,
          directory_enabled: false,
          sort_order: 70,
          layout_variant: "carousel",
          gallery_items: [
            { id: "dynamic-1", image_url: employeeAsset("dynamic-1.webp"), badge_mode: "none" },
            { id: "dynamic-2", image_url: employeeAsset("dynamic-2.webp"), badge_mode: "none" },
            { id: "dynamic-3", image_url: employeeAsset("dynamic-3.webp"), badge_mode: "none" },
            { id: "dynamic-4", image_url: employeeAsset("dynamic-4.webp"), badge_mode: "none" },
          ],
        },
        {
          id: "executive-video-history",
          type: "video_link",
          title: "往届世界会长大会精彩视频",
          visible: true,
          show_title: true,
          directory_enabled: false,
          sort_order: 80,
          video_url: "https://pubres.wshoto.com/base-material-server/wpDkH9EAAAzz_ESuYzhQ_DI5F3MfUnKA/17568884576262024骞绰犵5灞婁笘鐣屼細闀垮浼毬犻珮娓呰棰懧__x264_20250903_16282710_20250903_16320156.mp4",
          video_cover_url: employeeAsset("video-history.webp"),
        },
        {
          id: "executive-video-fifth",
          type: "video_link",
          title: "第五届世界会长大会精彩视频",
          visible: true,
          show_title: true,
          directory_enabled: false,
          sort_order: 90,
          video_url: "https://pubres.wshoto.com/base-material-server/wpDkH9EAAAzz_ESuYzhQ_DI5F3MfUnKA/1756888487066第五届世界会长大会播放视频1.mp4",
          video_cover_url: employeeAsset("video-fifth.webp"),
        },
        {
          id: "executive-conference-articles",
          type: "action_collection",
          title: "历届世界会长大会",
          visible: true,
          show_title: true,
          directory_enabled: false,
          sort_order: 100,
          layout_variant: "list",
          action_template: "articles",
          action_items: [
            { id: "conference-1", title: "首届世界会长大会在杭州隆重召开", summary: "畅通双循环、培育新优势、整合世界资源", source: "世界会长大会", image_url: employeeAsset("conference-1.jpg"), target_type: "external_url", target_value: "https://mp.weixin.qq.com/s/WLZ4kQRWP5NznbBKkSOU6A", open_mode: "new_tab" },
            { id: "conference-2", title: "第二届（2021）世界会长大会在杭州隆重召开", summary: "搭建交流平台，服务世界经济。", source: "世界会长大会", image_url: employeeAsset("conference-2.jpg"), target_type: "external_url", target_value: "https://mp.weixin.qq.com/s/6dgsOvvnutoHl0Kx3KPERA", open_mode: "new_tab" },
            { id: "conference-3", title: "第三届（2022）世界会长大会在中国杭州盛大开幕", source: "世界会长大会", image_url: employeeAsset("conference-3.jpg"), target_type: "external_url", target_value: "https://mp.weixin.qq.com/s/Ip-US3yO1p1rCq1gDNGQ2Q", open_mode: "new_tab" },
            { id: "conference-4", title: "第四届（2023）世界会长大会暨第14届西湖公共关系论坛在杭启幕", source: "世界会长大会", image_url: employeeAsset("conference-4.jpg"), target_type: "external_url", target_value: "https://mp.weixin.qq.com/s/0DNuL23CnjFvbU2Fvqdi0w", open_mode: "new_tab" },
            { id: "conference-5", title: "第五届（2024）世界会长大会在吉隆坡盛大启幕", source: "世界会长大会", image_url: employeeAsset("conference-5.jpg"), target_type: "external_url", target_value: "https://mp.weixin.qq.com/s/tis5WctlCRh9FL4A9v_GUw", open_mode: "new_tab" },
          ],
        },
        {
          id: "executive-activity-articles",
          type: "action_collection",
          title: "创非凡|精彩活动",
          visible: true,
          show_title: true,
          directory_enabled: false,
          sort_order: 110,
          layout_variant: "list",
          action_template: "articles",
          action_items: [
            { id: "activity-1", title: "TEAMATE数智体验中心盛大开业 共探数智科技新未来", source: "创非凡", image_url: employeeAsset("activity-1.jpg"), target_type: "external_url", target_value: "https://mp.weixin.qq.com/s/uonf9XzjjoYieiNqiWfB6g", open_mode: "new_tab" },
            { id: "activity-2", title: "“创新赋能 共建未来”座谈会", summary: "促进参会企业交流，汇聚企业核心背景与合作机会。", source: "创非凡", image_url: employeeAsset("activity-2.jpg"), target_type: "external_url", target_value: "https://page.weixin.qq.com/smartpage/p/b1_AfUA4gaZAHcBH16X4CXQZOVmB94", open_mode: "new_tab" },
            { id: "activity-3", title: "非凡领袖走进程前朋友圈游学：深化内容产出与认知边界新探索", summary: "商业底层模型框架分享", source: "创非凡", image_url: employeeAsset("activity-3.jpg"), target_type: "external_url", target_value: "https://mp.weixin.qq.com/s?__biz=MzkxMjY0NzY3MA==&mid=2247483732&idx=1&sn=00f08e2d77e514d2d6bfe383ff17f1f8&chksm=c108f5cdf67f7cdb2c943ce9a17bec60e355cd5e77f5ca607883364a481ca93b768ac7825129&mpshare=1&scene=1&srcid=0426tM3UeP4cgOL38BWqUtcM&sharer_shareinfo=4f34175eacc554754ff6c33a415a71fe&sharer_shareinfo_first=4f34175eacc554754ff6c33a415a71fe&from=industrynews&version=4.1.22.6014&platform=win#rd", open_mode: "new_tab" },
            { id: "activity-4", title: "“智汇全球，华为数字化与金融新趋势”——汇丰私人财富规划与非凡云社携手共绘未来蓝图", source: "创非凡", image_url: employeeAsset("activity-4.jpg"), target_type: "external_url", target_value: "https://mp.weixin.qq.com/s/4841HJA-tcSqToO447zKiA", open_mode: "new_tab" },
            { id: "activity-5", title: "非凡云社携手“交个朋友&重新加载” 开启游学新篇章", source: "创非凡", image_url: employeeAsset("activity-5.jpg"), target_type: "external_url", target_value: "https://mp.weixin.qq.com/s/QdCAIRdKXqiODrPr5wxi1Q", open_mode: "new_tab" },
          ],
        },
      ],
    } : null,
    policy_versions: {
      privacy: "mock-privacy-v1",
      chat_notice: "mock-chat-v1",
      lead_consent: "mock-lead-v1",
      profile_personalization: "mock-profile-v1",
    },
  };
}
