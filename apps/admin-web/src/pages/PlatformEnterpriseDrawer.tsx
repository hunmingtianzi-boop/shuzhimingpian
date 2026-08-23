import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
} from "@fluentui/react-components";
import { Open24Regular } from "@fluentui/react-icons";
import type { RefObject } from "react";

import { platformApi } from "../api/platformApi";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { navigate, platformEnterprisePath } from "../routing";
import { formatTimestamp, knowledgeStatusLabel } from "../utils/format";
import styles from "./PlatformEnterpriseDrawer.module.css";

type PlatformEnterpriseDrawerProps = {
  companyId: string;
  onClose: () => void;
  onChanged?: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
};

function closeAndFocus(
  onClose: () => void,
  returnFocusRef?: RefObject<HTMLElement | null>,
) {
  onClose();
  globalThis.setTimeout(() => returnFocusRef?.current?.focus(), 0);
}

export function PlatformEnterpriseDrawer({
  companyId,
  onClose,
  returnFocusRef,
}: PlatformEnterpriseDrawerProps) {
  const resource = useResource(
    () => platformApi.getEnterpriseDetail(companyId),
    companyId,
  );

  return (
    <Dialog open onOpenChange={(_, data) => !data.open && closeAndFocus(onClose, returnFocusRef)}>
      <DialogSurface className={styles.previewDialog}>
        <DialogBody>
          <DialogTitle>企业快速查看</DialogTitle>
          <DialogContent>
            {resource.status === "ready" && resource.data ? (
              <div className={styles.previewBody}>
                <div className={styles.previewHeader}>
                  <div>
                    <StatusBadge status={resource.data.status} />
                    <h2>{resource.data.companyName}</h2>
                    <p>
                      {resource.data.tenantName} · {resource.data.tenantSlug}
                    </p>
                  </div>
                  <Button
                    appearance="secondary"
                    icon={<Open24Regular />}
                    onClick={() => navigate(platformEnterprisePath(companyId, "overview"))}
                  >
                    打开完整详情
                  </Button>
                </div>

                <div className={styles.previewFacts}>
                  <div>
                    <span>入驻进度</span>
                    <strong>{knowledgeStatusLabel(resource.data.onboardingStatus)}</strong>
                  </div>
                  <div>
                    <span>资料完善度</span>
                    <strong>{resource.data.profileCompletion}%</strong>
                  </div>
                  <div>
                    <span>已发布名片</span>
                    <strong>{resource.data.publishedCardCount}</strong>
                  </div>
                  <div>
                    <span>最近更新</span>
                    <strong>{formatTimestamp(resource.data.updatedAt)}</strong>
                  </div>
                </div>

                <p className={styles.previewCopy}>
                  企业详情主流程已迁移到可刷新的独立页面；此处只保留快速跳转，不再承载完整八分区运营详情。
                </p>
              </div>
            ) : (
              <ResourceState
                status={resource.status === "ready" ? "empty" : resource.status}
                title={resource.status === "empty" ? "企业详情暂不可用" : undefined}
                description={resource.error?.message}
                errorCode={resource.error?.code}
                requestId={resource.error?.requestId}
                onRetry={resource.status === "error" ? resource.reload : undefined}
                compact
              />
            )}
          </DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={() => closeAndFocus(onClose, returnFocusRef)}>
              关闭
            </Button>
            <Button
              appearance="primary"
              onClick={() => {
                navigate(platformEnterprisePath(companyId, "overview"));
                closeAndFocus(onClose, returnFocusRef);
              }}
            >
              进入详情页
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}
