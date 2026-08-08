import { FluentProvider } from "@fluentui/react-components";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";
import { adminLightTheme } from "./theme";

const root = document.getElementById("root");
if (!root) throw new Error("Application root element is missing");
const applicationRoot = createRoot(root);

async function renderApplication() {
  const content = import.meta.env.DEV && window.location.pathname === "/__dev/card-editor"
    ? await import("./dev/StandaloneCardEditor").then(({ StandaloneCardEditor }) => (
        <StandaloneCardEditor />
      ))
    : <App />;

  applicationRoot.render(
    <StrictMode>
      <FluentProvider theme={adminLightTheme} className="fluent-root">
        {content}
      </FluentProvider>
    </StrictMode>,
  );
}

void renderApplication();
