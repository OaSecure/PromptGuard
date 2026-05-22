/** Owns the lifecycle of a DOM mutation watcher. */
export interface MutationWatcher {
  disconnect(): void;
}

/**
 * Watches a dynamic chat page and debounces input rediscovery.
 *
 * Chat UIs often replace composer elements during navigation or model changes.
 * Debouncing avoids repeatedly rescanning the DOM during a single render burst.
 */
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
