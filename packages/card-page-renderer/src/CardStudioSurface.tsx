import { useLayoutEffect, useMemo, useRef, type MutableRefObject, type ReactNode } from "react";

import surfaceStyles from "./card-studio-surface.css?inline";
import adapterStyles from "./card-studio-adapter.css?inline";

export type CardStudioSurfaceHandle = {
  findById: (id: string) => HTMLElement | null;
};

export function CardStudioSurface({
  children,
  mode,
  surfaceRef,
}: {
  children: ReactNode;
  mode: "public" | "editor";
  surfaceRef?: MutableRefObject<CardStudioSurfaceHandle | null>;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const scopedStyles = useMemo(
    () => `@scope (.card-studio-scope) {\n${surfaceStyles.replace(":root", ":scope")}\n${adapterStyles}\n}`,
    [],
  );

  useLayoutEffect(() => {
    if (!surfaceRef) return;
    surfaceRef.current = {
      findById: (id) => hostRef.current?.querySelector<HTMLElement>(`#${CSS.escape(id)}`) || null,
    };
    return () => {
      surfaceRef.current = null;
    };
  }, [surfaceRef]);

  const content = mode === "public" ? (
    <div className="public-shell"><div className="public-frame">{children}</div></div>
  ) : (
    <div className="editor-preview"><div className="public-frame">{children}</div></div>
  );

  return (
    <div ref={hostRef} className={`card-studio-host card-studio-scope card-studio-host--${mode}`}>
      <style>{scopedStyles}</style>
      {content}
    </div>
  );
}
