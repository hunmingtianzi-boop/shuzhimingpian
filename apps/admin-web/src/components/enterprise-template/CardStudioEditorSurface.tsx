import type { ReactNode } from "react";

import surfaceStyles from "../../../../../packages/card-page-renderer/src/card-studio-surface.css?inline";

const scopedSurfaceStyles = surfaceStyles
  .replace(/:root/g, ":scope")
  .replace(/@media/g, "@media");

const editorAdapterStyles = `
  .card-studio-editor-scope { width: 100%; height: 100%; min-height: 0; }
  .template-studio-dialog-body { display: block !important; width: 100vw !important; height: 100dvh !important; max-width: none !important; max-height: none !important; gap: 0 !important; overflow: clip !important; }
  .template-studio-shell { width: 100vw !important; max-width: none !important; height: 100dvh; min-width: 1120px; overflow: clip !important; }
  .template-studio-title-shell { min-height: 66px !important; padding: 0 !important; border: 0 !important; }
  .template-studio-title-shell,
  .template-composer-dialog-content { grid-column: 1 !important; }
  .template-studio-topbar { height: 66px; }
  .template-composer-dialog-content { min-height: 0; margin: 0 !important; overflow: hidden; }
  .enterprise-template-composer { height: 100%; }
  .enterprise-template-composer.studio-grid { grid-template-columns: 300px minmax(500px, 1fr) 356px; }
  .template-composer-pane { min-width: 0; min-height: 0; padding: 0; overflow: hidden; }
  .template-panel-tabs { position: static; margin: 0; }
  .template-panel-tabs .panel-tab { min-width: 0; }
  .template-inspector-heading { height: 54px; flex: 0 0 54px; }
  .template-module-library-v2 { display: block; }
  .template-module-library-v2 > div:first-child { display: grid; gap: 5px; margin-bottom: 14px; }
  .template-module-library-v2 > div:first-child > span { color: #6d7b8c; font-size: 10px; line-height: 1.55; }
  .template-module-library-v2 .template-module-library-actions { grid-template-columns: 1fr; gap: 8px; }
  .template-module-library-v2 .template-module-library-actions > button { min-height: 58px; padding: 10px 12px; }
  .template-module-library-v2 .template-module-library-actions > button > span { display: grid; min-width: 0; gap: 2px; }
  .template-module-library-v2 .template-module-library-actions strong { color: #26384b; font-size: 11px; line-height: 1.3; }
  .template-module-library-v2 .template-module-library-actions small { color: #778895; font-size: 9px; line-height: 1.4; }
  .template-structure-tab-content { padding-top: 0; }
  .template-canvas-pane { display: grid; grid-template-rows: 56px minmax(0, 1fr); }
  .template-canvas-toolbar { min-height: 56px; }
  .template-canvas-toolbar .template-preview-modes { flex: 0 0 auto; }
  .template-device-switch button { min-width: 36px; height: 30px; min-height: 30px; padding: 0; }
  .canvas-stage { position: relative; min-height: 0; }
  .template-open-public-link { display: block; width: max-content; margin: 12px auto 0; }
  .template-public-page-frame { width: 100%; min-height: 720px; border: 0; background: white; }
  .template-structure-list { list-style: none; margin: 0; padding: 0; }
  .template-structure-list > li + li { margin-top: 8px; }
  .template-structure-list .module-row { width: 100%; }
  .template-structure-list .module-name { cursor: pointer; }
  .studio-inspector-content > .inspector-section { margin-top: 20px; }
  .studio-inspector-content > .inspector-section { display: flex; flex-direction: column; }
  .studio-inspector-content > .inspector-section > h3 { order: -20; }
  .studio-inspector-content .template-identity-note { order: -10; }
  .studio-inspector-content .template-identity-presentation { order: -5; }
  .studio-inspector-content .template-inspector-visibility { order: 20; margin-top: 20px; padding-top: 18px; border-top: 1px solid #e2e9eb; }
  .studio-inspector-content .template-inspector-order { order: 21; }
  .studio-inspector-content .template-publish-checks { order: 30; }
  .studio-inspector-content .fui-Field { margin-top: 16px; }
  .studio-inspector-content .fui-Input,
  .studio-inspector-content .fui-Select,
  .studio-inspector-content .fui-Textarea { width: 100%; }
  .template-identity-source-summary { margin-top: 20px; }
  .template-composer-context,
  .template-save-notice,
  .template-composer-dialog-content > .feedback,
  .template-composer-dialog-content > .form-feedback { position: absolute; z-index: 30; top: 74px; left: 50%; max-width: 680px; transform: translateX(-50%); box-shadow: 0 10px 30px rgb(24 48 62 / 12%); }
  @media (max-width: 1180px) {
    .card-studio-editor-scope .template-studio-shell { min-width: 0 !important; max-width: 100vw; }
    .template-composer-dialog-content,
    .enterprise-template-composer.studio-grid { width: 100%; min-width: 0; max-width: 100vw; }
    .enterprise-template-composer.studio-grid { grid-template-columns: minmax(250px, .78fr) minmax(360px, 1.22fr); }
  }
  @media (max-width: 760px) {
    .template-studio-dialog-body,
    .template-studio-shell { width: 100% !important; min-width: 0; overflow: clip; }
    .enterprise-template-composer.studio-grid { display: block; }
    .template-studio-topbar { grid-template-columns: minmax(0, 1fr) auto; padding: 0 10px; }
    .template-studio-topbar .studio-history,
    .template-studio-topbar .studio-divider,
    .template-studio-topbar .autosave,
    .template-studio-actions .toolbar-button:not(.primary) { display: none; }
    .template-composer-title { gap: 7px; }
    .template-composer-title .document-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .template-studio-actions .toolbar-button.primary { min-height: 34px; padding: 0 10px; font-size: 11px; }
    .template-canvas-toolbar { padding: 8px; gap: 6px; overflow-x: auto; }
    .card-studio-editor-scope .canvas-stage { padding: 16px 0 !important; }
    .card-studio-editor-scope .editor-preview,
    .card-studio-editor-scope .editor-preview .public-frame { width: min(390px, 100%) !important; }
  }
`;

export function CardStudioEditorSurface({ children }: { children: ReactNode }) {
  return (
    <div className="card-studio-editor-scope">
      <style>{`@scope (.card-studio-editor-scope) {${scopedSurfaceStyles}}`}</style>
      <style>{editorAdapterStyles}</style>
      {children}
    </div>
  );
}
