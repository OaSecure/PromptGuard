import { describe, expect, it } from "vitest";
import { keyboardSendMethod } from "../../src/content/sendInterceptor";

describe("send interceptor keyboard classification", () => {
  it("classifies plain Enter as a send attempt", () => {
    expect(keyboardSendMethod(eventLike({ key: "Enter" }))).toBe("ENTER");
  });

  it("does not intercept text editing and IME composition Enter", () => {
    expect(keyboardSendMethod(eventLike({ key: "Enter", shiftKey: true }))).toBeNull();
    expect(keyboardSendMethod(eventLike({ key: "Enter", isComposing: true }))).toBeNull();
    expect(keyboardSendMethod(eventLike({ key: "a" }))).toBeNull();
  });
});

function eventLike(overrides: Partial<KeyboardEvent>): Pick<KeyboardEvent, "key" | "shiftKey" | "ctrlKey" | "altKey" | "metaKey" | "isComposing"> {
  return {
    key: overrides.key ?? "",
    shiftKey: overrides.shiftKey ?? false,
    ctrlKey: overrides.ctrlKey ?? false,
    altKey: overrides.altKey ?? false,
    metaKey: overrides.metaKey ?? false,
    isComposing: overrides.isComposing ?? false
  };
}
