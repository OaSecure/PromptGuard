/** UI state names shown while a preflight decision is pending or applied. */
export type OverlayDecision = "analyzing" | "warn" | "mask" | "block" | "error";

/** Describes one button rendered in the preflight overlay. */
export interface OverlayAction {
  id?: string;
  label: string;
  variant: "primary" | "secondary" | "danger";
  onClick: () => void;
}

/** Complete view model for one overlay render. */
export interface OverlayState {
  decision: OverlayDecision;
  message: string;
  evidence?: string[];
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

      const titleRow = doc.createElement("div");
      titleRow.style.display = "flex";
      titleRow.style.alignItems = "center";
      titleRow.style.gap = "10px";
      titleRow.style.marginBottom = "8px";
      container!.appendChild(titleRow);

      const icon = doc.createElement("span");
      icon.textContent = iconForDecision(state.decision);
      icon.setAttribute("aria-hidden", "true");
      icon.dataset.promptguardIcon = state.decision;
      applyIconStyle(icon, state.decision);
      titleRow.appendChild(icon);

      const title = doc.createElement("div");
      title.textContent = titleForDecision(state.decision);
      title.style.fontWeight = "700";
      title.style.fontSize = "16px";
      title.style.lineHeight = "1.25";
      titleRow.appendChild(title);

      const message = doc.createElement("div");
      message.textContent = state.message;
      message.style.fontSize = "14.5px";
      message.style.lineHeight = "1.5";
      message.style.marginBottom = "12px";
      container!.appendChild(message);

      if (state.evidence?.length) {
        const list = doc.createElement("ul");
        list.style.margin = "0 0 12px 0";
        list.style.padding = "0";
        list.style.listStyle = "none";
        list.style.display = "grid";
        list.style.gap = "6px";
        container!.appendChild(list);
        for (const item of state.evidence.slice(0, 4)) {
          const row = doc.createElement("li");
          row.textContent = item;
          row.style.fontSize = "13.5px";
          row.style.lineHeight = "1.45";
          row.style.padding = "8px 10px";
          row.style.borderRadius = "6px";
          row.style.background = evidenceBackground(state.decision);
          row.style.border = evidenceBorder(state.decision);
          list.appendChild(row);
        }
      }

      const actionRow = doc.createElement("div");
      actionRow.style.display = "flex";
      actionRow.style.gap = "8px";
      actionRow.style.justifyContent = "flex-end";
      for (const action of state.actions) {
        const button = doc.createElement("button");
        button.type = "button";
        button.textContent = action.label;
        button.dataset.promptguardAction = action.id ?? action.label.toLowerCase().replace(/\s+/g, "-");
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
      return "검사 중";
    case "warn":
      return "주의: 검토 필요";
    case "mask":
      return "마스킹: 대체문 준비";
    case "block":
      return "차단: 전송 중지";
    case "error":
      return "오류: 검사 실패";
  }
}

function iconForDecision(decision: OverlayDecision): string {
  switch (decision) {
    case "warn":
      return "!";
    case "mask":
      return "M";
    case "block":
      return "X";
    case "error":
      return "!";
    case "analyzing":
      return "i";
  }
}

function applyContainerStyle(container: HTMLElement): void {
  container.style.position = "fixed";
  container.style.right = "18px";
  container.style.bottom = "18px";
  container.style.zIndex = "2147483647";
  container.style.width = "min(390px, calc(100vw - 36px))";
  container.style.boxSizing = "border-box";
  container.style.padding = "16px";
  container.style.border = "1px solid #1f2937";
  container.style.borderRadius = "8px";
  container.style.background = "#ffffff";
  container.style.color = "#111827";
  container.style.boxShadow = "0 12px 32px rgba(15, 23, 42, 0.22)";
  container.style.fontFamily = "system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  container.style.display = "none";
}

function applyIconStyle(icon: HTMLElement, decision: OverlayDecision): void {
  icon.style.display = "inline-flex";
  icon.style.alignItems = "center";
  icon.style.justifyContent = "center";
  icon.style.flex = "0 0 auto";
  icon.style.width = "24px";
  icon.style.height = "24px";
  icon.style.borderRadius = "999px";
  icon.style.fontSize = "14px";
  icon.style.fontWeight = "800";
  icon.style.lineHeight = "1";
  icon.style.background = iconBackground(decision);
  icon.style.color = iconColor(decision);
  icon.style.border = iconBorder(decision);
}

function iconBackground(decision: OverlayDecision): string {
  if (decision === "block" || decision === "error") {
    return "#fee2e2";
  }
  if (decision === "warn" || decision === "mask") {
    return "#fef3c7";
  }
  return "#e0f2fe";
}

function iconColor(decision: OverlayDecision): string {
  if (decision === "block" || decision === "error") {
    return "#991b1b";
  }
  if (decision === "warn" || decision === "mask") {
    return "#92400e";
  }
  return "#075985";
}

function iconBorder(decision: OverlayDecision): string {
  if (decision === "block" || decision === "error") {
    return "1px solid #fecaca";
  }
  if (decision === "warn" || decision === "mask") {
    return "1px solid #f59e0b";
  }
  return "1px solid #7dd3fc";
}

function evidenceBackground(decision: OverlayDecision): string {
  if (decision === "block" || decision === "error") {
    return "#fef2f2";
  }
  if (decision === "warn" || decision === "mask") {
    return "#fffbeb";
  }
  return "#f8fafc";
}

function evidenceBorder(decision: OverlayDecision): string {
  if (decision === "block" || decision === "error") {
    return "1px solid #fecaca";
  }
  if (decision === "warn" || decision === "mask") {
    return "1px solid #fcd34d";
  }
  return "1px solid #e5e7eb";
}

function applyButtonStyle(button: HTMLButtonElement, variant: OverlayAction["variant"]): void {
  button.style.border = "1px solid #111827";
  button.style.borderRadius = "6px";
  button.style.padding = "8px 12px";
  button.style.fontSize = "14px";
  button.style.lineHeight = "1.2";
  button.style.cursor = "pointer";
  button.style.background = variant === "primary" ? "#111827" : "#ffffff";
  button.style.color = variant === "primary" ? "#ffffff" : "#111827";
  if (variant === "danger") {
    button.style.borderColor = "#b91c1c";
    button.style.color = "#b91c1c";
  }
}
