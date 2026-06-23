import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { createAnalyzeRequest, createComposerInput, createFileReferenceInput } from "../../src/shared/analyzeRequestBuilder";
import { isAnalyzeResponse } from "../../src/shared/responseValidation";
import type { AnalyzeResponse, DecisionAction, ExtensionContext } from "../../src/shared/types";

const context: ExtensionContext = { ai_service: "CHATGPT", ai_service_domain: "chatgpt.com", page_url_origin: "https://chatgpt.com",
  extension_version: "0.4.0", browser: "Chrome", locale: "ko-KR" };

describe("PR0 extension current behavior snapshots", () => {
  it("freezes all four accepted AnalyzeResponse action shapes", () => {
    const responses = (["Allow", "Warn", "Mask", "Block"] as DecisionAction[]).map(responseFor);
    expect(responses.every(isAnalyzeResponse)).toBe(true);
    expect(responses).toMatchSnapshot();
  });

  it("freezes composer and file-reference request payload", () => {
    const request = createAnalyzeRequest(context, "snapshot_config", [
      createComposerInput({ text: "composer snapshot text", inputMethod: "CLICK" }),
      createFileReferenceInput({ fileRef: "fref_snapshot_opaque", tempScopeId: "tscope_abcdefghijklmnopqrstuvwxyz123456", fileKind: "plain_text", extension: ".txt", mimeType: "text/plain", sizeBytes: 15 })
    ], "snapshot_request");
    const normalized = { ...request, inputs: request.inputs.map((input) => ({ ...input, input_id: "<GENERATED_ID>" })) };
    const fixturePath = resolve(process.cwd(), "tests/fixtures/current_behavior/request_builder.json");
    expect(normalized).toEqual(JSON.parse(readFileSync(fixturePath, "utf8")));
  });
});

function responseFor(action: DecisionAction): AnalyzeResponse {
  return { event_id: "evt_snapshot", request_id: "req_snapshot", action, checked_at: "2026-06-20T00:00:00Z",
    risk_score: action === "Allow" ? 0 : action === "Block" ? 95 : 80,
    risk_level: action === "Allow" ? "low" : action === "Block" ? "critical" : "high",
    user_message: "PromptGuard decision", allow_original_send: action === "Allow" || action === "Warn",
    requires_user_confirmation: action === "Warn", detections: [], input_results: [], content_unavailable_inputs: [],
    business_context_matches: [], client_request_id: "snapshot_request", filter_config_revision: "snapshot_config",
    ...(action === "Mask" ? { masked_prompt: "[SNAPSHOT_1]" } : {}) };
}
