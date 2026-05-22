export interface MutationWatcher {
  disconnect(): void;
}

export function watchInputArea(root: HTMLElement, callback: () => void, debounceMs = 150): MutationWatcher {
  let timeoutId: number | undefined;
  const observer = new MutationObserver(() => {
    if (timeoutId !== undefined) {
      window.clearTimeout(timeoutId);
    }
    timeoutId = window.setTimeout(callback, debounceMs);
  });

  observer.observe(root, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["contenteditable", "style", "class", "aria-label"]
  });

  return {
    disconnect() {
      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
      }
      observer.disconnect();
    }
  };
}
