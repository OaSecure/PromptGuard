/** UI state names shown while a preflight decision is pending or applied. */
export type OverlayDecision = "analyzing" | "warn" | "mask" | "block" | "error";

/** Describes one button rendered in the preflight overlay. */
export interface OverlayAction {
  label: string;
  variant: "primary" | "secondary" | "danger";
  onClick: () => void;
}

/** Complete view model for one overlay render. */
export interface OverlayState {
  decision: OverlayDecision;
  message: string;
  actions: OverlayAction[];
}

/** Public overlay operations used by prompt and file controllers. */
export interface PreflightOverlay {
  show(state: OverlayState): void;
  hide(): void;
  destroy(): void;
}

const CONTAINER_ID = "promptguard-preflight-overlay";

/**
 * Creates or reuses the page-level PromptGuard overlay.
 *
 * The overlay renders fixed safe messages from controllers rather than raw
 * server `user_message` text, keeping detected values out of the DOM.
 */
export function createPreflightOverlay(doc: Document = document): PreflightOverlay {
  let container = doc.getElementById(CONTAINER_ID);
  if (!container) {
    container = doc.createElement("div");
    container.id = CONTAINER_ID;
    container.setAttribute("role", "dialog");
    container.setAttribute("aria-live", "polite");
    (doc.body ?? doc.documentElement).appendChild(container);
  }

  applyContainerStyle(container);

  return {
    show(state) {
      container!.replaceChildren();
      container!.dataset.promptguardDecision = state.decision;
      container!.style.display = "block";

      const title = doc.createElement("div");
      title.textContent = titleForDecision(state.decision);
      title.style.fontWeight = "700";
      title.style.marginBottom = "6px";
      container!.appendChild(title);

      const message = doc.createElement("div");
      message.textContent = state.message;
      message.style.fontSize = "13px";
      message.style.lineHeight = "1.4";
      message.style.marginBottom = "10px";
      container!.appendChild(message);

      const actionRow = doc.createElement("div");
      actionRow.style.display = "flex";
      actionRow.style.gap = "8px";
      actionRow.style.justifyContent = "flex-end";
      for (const action of state.actions) {
        const button = doc.createElement("button");
        button.type = "button";
        button.textContent = action.label;
        button.dataset.promptguardAction = action.label.toLowerCase().replace(/\s+/g, "-");
        applyButtonStyle(button, action.variant);
        button.addEventListener("click", action.onClick);
        actionRow.appendChild(button);
      }
      container!.appendChild(actionRow);
    },
    hide() {
      container!.style.display = "none";
      container!.replaceChildren();
      delete container!.dataset.promptguardDecision;
    },
    destroy() {
      container!.remove();
    }
  };
}

function titleForDecision(decision: OverlayDecision): string {
  switch (decision) {
    case "analyzing":
      return "PromptGuard";
    case "warn":
      return "Review before sending";
    case "mask":
      return "Masked replacement available";
    case "block":
      return "Send blocked";
    case "error":
      return "Inspection unavailable";
  }
}

function applyContainerStyle(container: HTMLElement): void {
  container.style.position = "fixed";
  container.style.right = "18px";
  container.style.bottom = "18px";
  container.style.zIndex = "2147483647";
  container.style.width = "min(360px, calc(100vw - 36px))";
  container.style.boxSizing = "border-box";
  container.style.padding = "14px";
  container.style.border = "1px solid #1f2937";
  container.style.borderRadius = "8px";
  container.style.background = "#ffffff";
  container.style.color = "#111827";
  container.style.boxShadow = "0 12px 32px rgba(15, 23, 42, 0.22)";
  container.style.fontFamily = "system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  container.style.display = "none";
}

function applyButtonStyle(button: HTMLButtonElement, variant: OverlayAction["variant"]): void {
  button.style.border = "1px solid #111827";
  button.style.borderRadius = "6px";
  button.style.padding = "7px 10px";
  button.style.fontSize = "13px";
  button.style.cursor = "pointer";
  button.style.background = variant === "primary" ? "#111827" : "#ffffff";
  button.style.color = variant === "primary" ? "#ffffff" : "#111827";
  if (variant === "danger") {
    button.style.borderColor = "#b91c1c";
    button.style.color = "#b91c1c";
  }
}
