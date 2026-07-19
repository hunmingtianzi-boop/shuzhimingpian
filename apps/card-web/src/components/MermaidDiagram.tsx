import { useEffect, useId, useState } from "react";

type MermaidStatus = "loading" | "ready" | "error";

let mermaidLoader: Promise<typeof import("mermaid")["default"]> | undefined;
let renderSequence = 0;

function loadMermaid() {
  mermaidLoader ??= import("mermaid").then(({ default: mermaid }) => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      suppressErrorRendering: true,
      maxTextSize: 12_000,
      maxEdges: 120,
      theme: "base",
      themeVariables: {
        background: "#061310",
        primaryColor: "#10221f",
        primaryTextColor: "#eaf4f2",
        primaryBorderColor: "#55dcef",
        secondaryColor: "#0b1c19",
        secondaryTextColor: "#d1dfdc",
        secondaryBorderColor: "#5f8f8c",
        tertiaryColor: "#071512",
        tertiaryTextColor: "#d1dfdc",
        tertiaryBorderColor: "#416b68",
        lineColor: "#75aaa7",
        textColor: "#dbe7e5",
        mainBkg: "#10221f",
        nodeBorder: "#55dcef",
        clusterBkg: "#091816",
        clusterBorder: "#416b68",
        edgeLabelBackground: "#061310",
        fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
        fontSize: "13px",
      },
      flowchart: {
        htmlLabels: false,
        useMaxWidth: true,
        curve: "linear",
        nodeSpacing: 28,
        rankSpacing: 34,
        padding: 12,
      },
    });
    return mermaid;
  });
  return mermaidLoader;
}

export function MermaidDiagram({ source }: { source: string }) {
  const stableId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const [status, setStatus] = useState<MermaidStatus>("loading");
  const [svg, setSvg] = useState("");

  useEffect(() => {
    let cancelled = false;
    const normalized = source.trim();
    setStatus("loading");
    setSvg("");

    if (!normalized) {
      setStatus("error");
      return () => {
        cancelled = true;
      };
    }

    const timeoutId = window.setTimeout(() => {
      void loadMermaid()
        .then((mermaid) => {
          renderSequence += 1;
          return mermaid.render(`assistant-diagram-${stableId}-${renderSequence}`, normalized);
        })
        .then((result) => {
          if (cancelled) return;
          setSvg(result.svg);
          setStatus("ready");
        })
        .catch(() => {
          if (cancelled) return;
          setStatus("error");
        });
    }, 180);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [source, stableId]);

  return (
    <figure className="message-diagram">
      <figcaption>图示</figcaption>
      {status === "loading" && (
        <div className="message-diagram-loading" aria-label="正在绘制图示">
          <i />
          <i />
          <i />
        </div>
      )}
      {status === "ready" && (
        <div
          className="message-diagram-canvas"
          role="img"
          aria-label="AI 生成的关系图"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      )}
      {status === "error" && (
        <div className="message-diagram-error" role="note">
          <strong>图示语法暂时无法解析</strong>
          <pre><code>{source}</code></pre>
        </div>
      )}
    </figure>
  );
}
