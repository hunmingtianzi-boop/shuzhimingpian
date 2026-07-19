import {
  Children,
  isValidElement,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { MermaidDiagram } from "./MermaidDiagram";

function safeExternalHref(href: string | undefined): string | undefined {
  if (!href) return undefined;
  const normalized = href.trim();
  return /^(https?:\/\/|mailto:)/i.test(normalized) ? normalized : undefined;
}

function MarkdownLink({ href, children }: ComponentPropsWithoutRef<"a">) {
  const safeHref = safeExternalHref(href);
  if (!safeHref) return <>{children}</>;

  return (
    <a href={safeHref} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  );
}

function MarkdownPre({ children, ...props }: ComponentPropsWithoutRef<"pre">) {
  const child = Children.toArray(children)[0];
  if (
    Children.count(children) === 1 &&
    isValidElement<{ className?: string; children?: ReactNode }>(child) &&
    child.props.className?.split(/\s+/).includes("language-mermaid")
  ) {
    const source = Children.toArray(child.props.children).join("").replace(/\n$/, "");
    return <MermaidDiagram source={source} />;
  }

  return <pre {...props}>{children}</pre>;
}

const markdownComponents: Components = {
  a: ({ node: _node, ...props }) => <MarkdownLink {...props} />,
  blockquote: ({ node: _node, ...props }) => (
    <blockquote className="message-note" {...props} />
  ),
  h2: ({ node: _node, ...props }) => <h2 className="message-section-title" {...props} />,
  h3: ({ node: _node, ...props }) => <h3 className="message-section-title" {...props} />,
  h4: ({ node: _node, ...props }) => <h4 className="message-section-title" {...props} />,
  ol: ({ node: _node, ...props }) => <ol className="message-flow" {...props} />,
  pre: ({ node: _node, ...props }) => <MarkdownPre {...props} />,
  table: ({ node: _node, ...props }) => (
    <div
      className="message-table-scroll"
      role="region"
      aria-label="回答数据表"
      tabIndex={0}
    >
      <table {...props} />
    </div>
  ),
  ul: ({ node: _node, ...props }) => <ul className="message-point-list" {...props} />,
};

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="message-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
