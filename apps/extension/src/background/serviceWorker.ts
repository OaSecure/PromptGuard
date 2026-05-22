import { routeMessage } from "./messageRouter";
import { isExtensionMessage } from "../shared/messageTypes";

chrome.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
  if (!isExtensionMessage(message)) {
    sendResponse({ code: "UNKNOWN_ERROR", message: "Unsupported message shape." });
    return false;
  }

  routeMessage(message).then(sendResponse).catch(() => {
    sendResponse({ code: "UNKNOWN_ERROR", message: "Message handling failed." });
  });

  return true;
});
