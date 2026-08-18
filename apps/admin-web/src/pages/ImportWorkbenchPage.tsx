import { KnowledgeImportPanel } from "../components/KnowledgeImportPanel";
import { PageHeader } from "../components/PageHeader";

export function ImportWorkbenchPage() {
  const focusRunId = typeof window === "undefined"
    ? undefined
    : new URLSearchParams(window.location.search).get("run") ?? undefined;
  return (
    <main className="page-stack import-workbench-page">
      <PageHeader
        title="资料导入工作台"
        description="上传企业材料，由智能整理生成企业资料、核心业务、案例和 FAQ 候选；确认后写入对应工作台草稿。"
      />
      <KnowledgeImportPanel focusRunId={focusRunId} />
    </main>
  );
}
