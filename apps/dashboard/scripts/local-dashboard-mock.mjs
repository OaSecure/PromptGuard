import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const host = process.env.HOST || "localhost";
const port = Number(process.env.PORT || 5173);

const csrfTokens = new Set();
const sessions = new Set();

const users = [
  {
    id: "local-admin",
    login_id: "admin",
    username: "Admin",
    department: "Security",
    display_name: "Local Admin",
    role: "ADMIN",
    status: "ACTIVE",
    created_at: "2026-06-25T00:00:00.000Z",
    updated_at: "2026-06-25T00:00:00.000Z",
  },
  {
    id: "local-user",
    login_id: "analyst",
    username: "Analyst",
    department: "Ops",
    display_name: "Security Analyst",
    role: "USER",
    status: "ACTIVE",
    created_at: "2026-06-25T00:00:00.000Z",
    updated_at: "2026-06-25T00:00:00.000Z",
  },
];

let filterRules = [
  {
    id: "mock-keyword-api-key",
    origin: "custom",
    kind: "keyword",
    category: "인증 정보",
    label: "API 키 키워드",
    description: "로컬 대시보드 개발용 키워드 규칙입니다.",
    placeholder: "SECRET_TOKEN",
    severity: "high",
    action: "MASK",
    enabled: true,
    editable_fields: {
      category: true,
      label: true,
      description: true,
      placeholder: true,
      severity: true,
      action: true,
      enabled: true,
      config_json: true,
    },
    config_json: {
      keywords: ["api_key", "secret"],
      exclusion_keywords: ["public"],
    },
    created_at: "2026-06-25T00:00:00.000Z",
    updated_at: "2026-06-25T00:00:00.000Z",
    archived_at: null,
  },
  {
    id: "mock-built-in-email",
    origin: "built_in",
    kind: "detector",
    category: "개인정보",
    label: "이메일 탐지",
    description: "로컬 대시보드 개발용 기본 탐지 규칙입니다.",
    placeholder: "EMAIL",
    severity: "medium",
    action: "WARN",
    enabled: true,
    editable_fields: {
      severity: true,
      action: true,
      enabled: true,
    },
    config_json: null,
    created_at: "2026-06-25T00:00:00.000Z",
    updated_at: "2026-06-25T00:00:00.000Z",
    archived_at: null,
  },
];

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

function sendJson(response, status, body, headers = {}) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    ...headers,
  });
  response.end(JSON.stringify(body));
}

function parseCookies(header = "") {
  return Object.fromEntries(
    header
      .split(";")
      .map((cookie) => cookie.trim())
      .filter(Boolean)
      .map((cookie) => {
        const index = cookie.indexOf("=");
        return index === -1 ? [cookie, ""] : [cookie.slice(0, index), decodeURIComponent(cookie.slice(index + 1))];
      }),
  );
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : {};
}

function currentUser(request) {
  const cookies = parseCookies(request.headers.cookie);
  return sessions.has(cookies.promptguard_dashboard_session) ? users[0] : null;
}

function requireSession(request, response) {
  const user = currentUser(request);
  if (user) return user;
  sendJson(response, 401, { detail: "invalid dashboard session" });
  return null;
}

function userResponse(user) {
  return {
    id: user.id,
    login_id: user.login_id,
    username: user.username,
    department: user.department,
    display_name: user.display_name,
    role: user.role,
    status: user.status,
  };
}

async function handleApi(request, response, pathname) {
  if (request.method === "GET" && pathname === "/dashboard/session/csrf") {
    const csrfToken = crypto.randomUUID();
    csrfTokens.add(csrfToken);
    sendJson(response, 200, { csrf_token: csrfToken }, {
      "Set-Cookie": `promptguard_dashboard_csrf=${encodeURIComponent(csrfToken)}; Path=/; SameSite=Lax`,
    });
    return true;
  }

  if (request.method === "POST" && pathname === "/dashboard/session/login") {
    const csrfToken = String(request.headers["x-csrf-token"] || "");
    const body = await readJson(request);
    if (!csrfTokens.has(csrfToken)) {
      sendJson(response, 403, { detail: "csrf token mismatch" });
      return true;
    }
    if (body.login_id !== "admin" || body.password !== "1234") {
      sendJson(response, 401, { detail: "invalid credentials" });
      return true;
    }

    const sessionToken = crypto.randomUUID();
    const nextCsrfToken = crypto.randomUUID();
    sessions.add(sessionToken);
    csrfTokens.add(nextCsrfToken);
    sendJson(response, 200, {
      ok: true,
      user: userResponse(users[0]),
      csrf_token: nextCsrfToken,
      expires_at: new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString(),
    }, {
      "Set-Cookie": [
        `promptguard_dashboard_session=${encodeURIComponent(sessionToken)}; Path=/; SameSite=Lax`,
        `promptguard_dashboard_csrf=${encodeURIComponent(nextCsrfToken)}; Path=/; SameSite=Lax`,
      ],
    });
    return true;
  }

  if (request.method === "GET" && pathname === "/dashboard/session/me") {
    const user = requireSession(request, response);
    if (!user) return true;
    sendJson(response, 200, userResponse(user));
    return true;
  }

  if (request.method === "POST" && pathname === "/dashboard/session/logout") {
    const cookies = parseCookies(request.headers.cookie);
    sessions.delete(cookies.promptguard_dashboard_session);
    sendJson(response, 204, undefined, {
      "Set-Cookie": [
        "promptguard_dashboard_session=; Path=/; Max-Age=0; SameSite=Lax",
        "promptguard_dashboard_csrf=; Path=/; Max-Age=0; SameSite=Lax",
      ],
    });
    return true;
  }

  if (pathname.startsWith("/dashboard/") && !requireSession(request, response)) return true;

  if (request.method === "GET" && pathname === "/dashboard/users") {
    sendJson(response, 200, users);
    return true;
  }

  if (request.method === "GET" && pathname === "/dashboard/filters") {
    sendJson(response, 200, filterRules);
    return true;
  }

  if (request.method === "POST" && pathname === "/dashboard/filters") {
    const body = await readJson(request);
    const now = new Date().toISOString();
    const rule = {
      id: `mock-custom-${crypto.randomUUID()}`,
      origin: "custom",
      kind: body.kind || "keyword",
      category: body.category || "Custom",
      label: body.label || "Custom rule",
      description: body.description ?? null,
      placeholder: body.placeholder ?? null,
      severity: body.severity || "medium",
      action: body.action || "MASK",
      enabled: body.enabled !== false,
      editable_fields: {
        category: true,
        label: true,
        description: true,
        placeholder: true,
        severity: true,
        action: true,
        enabled: true,
        config_json: true,
      },
      config_json: body.config_json ?? null,
      created_at: now,
      updated_at: now,
      archived_at: null,
    };
    filterRules = [rule, ...filterRules];
    sendJson(response, 200, rule);
    return true;
  }

  const filterMatch = pathname.match(/^\/dashboard\/filters\/([^/]+)(?:\/(enable|disable))?$/);
  if (filterMatch && request.method === "PATCH") {
    const [, id, stateAction] = filterMatch;
    const body = stateAction ? {} : await readJson(request);
    const rule = filterRules.find((item) => item.id === id);
    if (!rule) {
      sendJson(response, 404, { detail: "filter rule not found" });
      return true;
    }
    if (stateAction) {
      rule.enabled = stateAction === "enable";
    } else {
      rule.severity = body.severity ?? rule.severity;
      rule.action = body.action ?? rule.action;
      rule.enabled = body.enabled ?? rule.enabled;
      if (rule.origin === "custom") {
        rule.category = body.category ?? rule.category;
        rule.label = body.label ?? rule.label;
        rule.description = body.description ?? rule.description;
        rule.placeholder = body.placeholder ?? rule.placeholder;
        rule.config_json = body.config_json ?? rule.config_json;
      }
    }
    rule.updated_at = new Date().toISOString();
    sendJson(response, 200, rule);
    return true;
  }

  if (filterMatch && request.method === "DELETE") {
    const [, id] = filterMatch;
    filterRules = filterRules.filter((item) => item.id !== id || item.origin === "built_in");
    sendJson(response, 204);
    return true;
  }

  if (request.method === "POST" && pathname === "/dashboard/filters/dry-run") {
    const body = await readJson(request);
    const sample = String(body.sample_text ?? "");
    const matched = /api[_-]?key|secret|email|@/i.test(sample);
    sendJson(response, 200, {
      matched,
      expected_action: matched ? "MASK" : "ALLOW",
      expected_severity: matched ? "high" : "low",
      match_count: matched ? 1 : 0,
      reason_code: matched ? "MOCK_FILTER_MATCH" : "MOCK_NO_MATCH",
      matched_keywords: matched ? ["mock"] : [],
      evidence_counts: matched ? { mock: 1 } : {},
      sample_persisted: false,
    });
    return true;
  }

  if (request.method === "GET" && pathname === "/dashboard/overview") {
    sendJson(response, 200, {
      total_events: 128,
      blocked_events: 18,
      warned_events: 31,
      active_users: users.filter((user) => user.status === "ACTIVE").length,
      recent_events: [],
      top_rules: [],
    });
    return true;
  }

  if (request.method === "GET" && pathname === "/dashboard/status") {
    sendJson(response, 200, {
      api: { status: "ok", latency_ms: 12 },
      database: { status: "mocked" },
      classifier: { status: "disabled-local-mock" },
      verifier: { status: "disabled-local-mock" },
      admin_local_api_origin: `http://${host}:${port}`,
    });
    return true;
  }

  sendJson(response, 404, { detail: `No mock route for ${request.method} ${pathname}` });
  return true;
}

function serveStatic(request, response, pathname) {
  const routePath = pathname === "/" ? "/login.html" : decodeURIComponent(pathname);
  const filePath = path.resolve(root, routePath.replace(/^\/+/, ""));
  if (!filePath.startsWith(root)) {
    response.writeHead(403);
    response.end("Forbidden");
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      response.writeHead(404);
      response.end("Not found");
      return;
    }
    response.writeHead(200, {
      "Content-Type": contentTypes[path.extname(filePath)] || "application/octet-stream",
    });
    response.end(data);
  });
}

const server = http.createServer(async (request, response) => {
  try {
    const requestUrl = new URL(request.url || "/", `http://${host}:${port}`);
    if (requestUrl.pathname.startsWith("/dashboard/")) {
      await handleApi(request, response, requestUrl.pathname);
      return;
    }
    serveStatic(request, response, requestUrl.pathname);
  } catch (error) {
    sendJson(response, 500, { detail: error instanceof Error ? error.message : "mock server error" });
  }
});

server.listen(port, host, () => {
  console.log(`Local dashboard mock: http://${host}:${port}/login.html`);
  console.log("Mock account: admin / 1234");
  console.log("Open admin redirect shell: /admin.html, users admin page: /users.html");
});
