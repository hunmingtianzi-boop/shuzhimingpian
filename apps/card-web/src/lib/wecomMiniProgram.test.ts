import { describe, expect, it } from "vitest";

import { isWeComMiniProgramTarget, parseWeComMiniProgramTarget } from "./wecomMiniProgram";

describe("WeCom mini-program action targets", () => {
  it("parses the embedded app id and page route", () => {
    expect(parseWeComMiniProgramTarget(
      "/__wecom/miniprogram?app_id=wxe79dc0e12345620d&path=pages%2Findex%2Fdiy.html%3Fid%3D11",
    )).toEqual({
      appId: "wxe79dc0e12345620d",
      path: "pages/index/diy.html?id=11",
    });
  });

  it("rejects arbitrary internal paths and malformed app ids", () => {
    expect(isWeComMiniProgramTarget("/c/xusongbo")).toBe(false);
    expect(isWeComMiniProgramTarget(
      "/__wecom/miniprogram?app_id=not-wechat&path=pages%2Findex%2Findex.html",
    )).toBe(false);
  });
});
