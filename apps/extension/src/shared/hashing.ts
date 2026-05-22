export function createClientRequestId(prefix: "crq" | "frq" | "file" = "crq"): string {
  const random = new Uint32Array(2);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(random);
  } else {
    random[0] = Math.floor(Math.random() * Number.MAX_SAFE_INTEGER);
    random[1] = Date.now();
  }
  return `${prefix}_${Date.now().toString(36)}_${Array.from(random)
    .map((part) => part.toString(36))
    .join("")}`;
}
