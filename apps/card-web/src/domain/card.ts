export type ActionKind = "anchor" | "external" | "assistant";

export type AnchorAction = {
  kind: "anchor";
  label: string;
  target: string;
};

export type ExternalAction = {
  kind: "external";
  label: string;
  target: string;
};

export type AssistantAction = {
  kind: "assistant";
  label: string;
  target: string;
};

export type CardAction = AnchorAction | ExternalAction | AssistantAction;

export type MediaAsset = {
  src: string;
  alt: string;
  caption?: string;
  width?: number;
  height?: number;
};

export type KnowledgeItem = {
  id: string;
  question: string;
  shortQuestion: string;
  answer: string;
  keywords: string[];
  source: string;
};

export type KnowledgeFallback = {
  answer: string;
  source: string;
};

export type SeoConfig = {
  title: string;
  description: string;
};

export type BrandConfig = {
  name: string;
  shortName: string;
  tagline: string;
  headerDescriptor: string;
  logo: MediaAsset;
  homeAriaLabel: string;
  officialAction: ExternalAction;
};

export type ThemeTokens = {
  accent: string;
  accentStrong: string;
  accentSoft: string;
  background: string;
  surface: string;
  surfaceRaised: string;
  surfaceMuted: string;
  text: string;
  textSoft: string;
  textFaint: string;
  line: string;
  lineStrong: string;
  shadow: string;
};

export type ThemeConfig = {
  defaultMode: "system" | "light" | "dark";
  action: string;
  onAction: string;
  light: ThemeTokens;
  dark: ThemeTokens;
  heroOverlay: {
    light: string;
    dark: string;
  };
  radiusCard: string;
  radiusControl: string;
  radiusSmall: string;
};

export type MetricItem = {
  value: string;
  label: string;
  note: string;
};

export type HeroConfig = {
  id: string;
  kicker: string;
  titleLines: string[];
  summary: string;
  art: MediaAsset;
  actions: CardAction[];
  metrics: MetricItem[];
};

export type BaseSection = {
  id: string;
  navLabel: string;
  showInNav: boolean;
  eyebrow?: string;
  heading: string;
  description: string;
};

export type BusinessItem = {
  icon: string;
  eyebrow: string;
  title: string;
  description: string;
  status: string;
  points: string[];
};

export type FeatureGridSection = BaseSection & {
  type: "feature-grid";
  businesses: BusinessItem[];
};

export type CapabilityItem = {
  icon: string;
  title: string;
  description: string;
};

export type MediaShowcaseSection = BaseSection & {
  type: "media-showcase";
  capabilities: CapabilityItem[];
  action: CardAction;
  visualLabel: string;
  visualTitle: string;
  visual: MediaAsset;
};

export type JourneyStep = {
  title: string;
  text: string;
  path?: "shared" | "branch-a" | "branch-b";
};

export type AudienceItem = {
  icon: string;
  title: string;
  description: string;
};

export type ProcessSection = BaseSection & {
  type: "process";
  steps: JourneyStep[];
  audienceHeading: string;
  audiences: AudienceItem[];
};

export type EvidenceSection = BaseSection & {
  type: "evidence";
  visual: MediaAsset;
  headlineMetric: string;
  metricDescription: string;
  themesAriaLabel: string;
  themes: string[];
  caveat: string;
  supportHeading: string;
  supportNote: string;
  supportNames: string[];
};

export type CooperationStep = {
  title: string;
  text: string;
};

export type CooperationCta = {
  title: string;
  description: string;
  action: CardAction;
};

export type EngagementSection = BaseSection & {
  type: "engagement";
  steps: CooperationStep[];
  cta: CooperationCta;
};

export type FaqSection = BaseSection & {
  type: "faq";
  itemIds: string[];
  action?: CardAction;
};

export type ClosingSection = BaseSection & {
  type: "closing";
  art: MediaAsset;
  actions: CardAction[];
};

export type AssistantMessage = {
  text: string;
  source: string;
};

export type AssistantLabels = {
  closeBackdrop: string;
  closeButton: string;
  quickQuestions: string;
  quickQuestionsIntro: string;
  loading: string;
  input: string;
  placeholder: string;
  send: string;
  sourcePrefix: string;
};

export type AssistantConfig = {
  title: string;
  status: string;
  subtitle: string;
  launcherAriaLabel: string;
  launcherKicker: string;
  launcherLabel: string;
  initialMessage: AssistantMessage;
  quickQuestionIds: string[];
  labels: AssistantLabels;
  disclaimer: string;
  knowledgeBase: KnowledgeItem[];
  fallback: KnowledgeFallback;
};

export type FooterConfig = {
  brandNote: string;
  disclaimer: string;
  backToTopAction: CardAction;
};

export type ResponsiveMediaAsset = MediaAsset & {
  srcSet?: string;
  sizes?: string;
};

export type CardSolution = {
  id: string;
  title: string;
  description: string;
};

export type CardCaseStudy = {
  title: string;
  category: string;
  description: string;
  detail: string;
  visual: ResponsiveMediaAsset;
};

export type OwnerExperience = {
  period: string;
  organization: string;
  role: string;
  description: string;
};

export type OwnerPresentation = {
  demoLabel: string;
  name: string;
  role: string;
  summary: string;
  valueProposition: string;
  capabilities: string[];
  experiences: OwnerExperience[];
  portrait: ResponsiveMediaAsset;
};

export type AssistantRecommendation = {
  title: string;
  description: string;
  question: string;
};

export type CardPresentation = {
  /** Keep a reviewed homepage narrative instead of replacing it with raw catalog copy. */
  homepageContentMode?: "curated" | "published";
  heroVisual: ResponsiveMediaAsset;
  heroSummary?: string;
  solutions: CardSolution[];
  caseStudy: CardCaseStudy;
  owner: OwnerPresentation;
  assistantVisual: ResponsiveMediaAsset;
  assistantQuestionIds?: string[];
  assistantRecommendations: AssistantRecommendation[];
};

export type EnterpriseCardSection =
  | FeatureGridSection
  | MediaShowcaseSection
  | ProcessSection
  | EvidenceSection
  | EngagementSection
  | FaqSection
  | ClosingSection;

export type EnterpriseCardConfig = {
  id: string;
  version: string;
  /** Marks a configuration-only shell that must never look like a published enterprise. */
  isBlankTemplate?: boolean;
  seo: SeoConfig;
  brand: BrandConfig;
  theme: ThemeConfig;
  hero: HeroConfig;
  sections: EnterpriseCardSection[];
  assistant: AssistantConfig;
  footer: FooterConfig;
  /** Optional visitor-card fallback presentation. Published API data overrides matching fields. */
  presentation?: CardPresentation;
};
