import { Button } from "@fluentui/react-components";
import { DocumentArrowUp24Regular } from "@fluentui/react-icons";

import { APP_PATHS, navigate } from "../routing";

export function ImportWorkbenchButton() {
  return (
    <Button icon={<DocumentArrowUp24Regular />} onClick={() => navigate(APP_PATHS.imports)}>
      导入资料
    </Button>
  );
}
