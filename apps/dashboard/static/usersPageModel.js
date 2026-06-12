import { dashboardFallbackMessage } from "./dashboardFallback.js";
const TABLE_COLUMNS = [
    "login_id",
    "username",
    "department",
    "role",
    "status",
    "last_login_at",
    "last_event_at",
    "created_at",
    "event_count",
    "blocked_count",
    "masked_count",
    "warned_count",
];
const SAFE_EMPTY_VALUE = "-";
function formatCount(value) {
    return new Intl.NumberFormat("en-US").format(value);
}
function formatDateTime(value) {
    if (!value)
        return SAFE_EMPTY_VALUE;
    const date = new Date(value);
    if (Number.isNaN(date.getTime()))
        return SAFE_EMPTY_VALUE;
    return new Intl.DateTimeFormat("ko-KR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
}
function columnText(user, column) {
    switch (column) {
        case "login_id":
            return user.login_id;
        case "username":
            return user.username;
        case "department":
            return user.department?.trim() || SAFE_EMPTY_VALUE;
        case "role":
            return user.role;
        case "status":
            return user.status;
        case "last_login_at":
            return formatDateTime(user.last_login_at);
        case "last_event_at":
            return formatDateTime(user.last_event_at);
        case "created_at":
            return formatDateTime(user.created_at);
        case "event_count":
            return formatCount(user.event_count);
        case "blocked_count":
            return formatCount(user.blocked_count);
        case "masked_count":
            return formatCount(user.masked_count);
        case "warned_count":
            return formatCount(user.warned_count);
    }
}
function columnTone(column) {
    if (column === "role")
        return "role";
    if (column === "status")
        return "status";
    if (column.endsWith("_count") || column === "event_count")
        return "count";
    return "default";
}
export function projectUserTableRows(users) {
    return users.map((user) => ({
        loginId: user.login_id,
        cells: TABLE_COLUMNS.map((column) => ({
            key: column,
            text: columnText(user, column),
            tone: columnTone(column),
        })),
    }));
}
export function deriveUsersScreenState(users, hadError) {
    if (hadError) {
        return { kind: "error", message: dashboardFallbackMessage("error") };
    }
    if (users.length === 0) {
        return { kind: "empty", message: dashboardFallbackMessage("empty") };
    }
    return { kind: "ready", message: "" };
}
export function loadingUsersScreenState() {
    return { kind: "loading", message: dashboardFallbackMessage("loading") };
}
export function safeUsersMutationErrorMessage(status) {
    if (status === 400 || status === 409 || status === 422) {
        return "입력값을 확인해 주세요.";
    }
    if (status === 401 || status === 403) {
        return "대시보드 권한 또는 보안 토큰을 확인할 수 없습니다. 다시 로그인해 주세요.";
    }
    if (status === 404) {
        return "대상 사용자를 찾을 수 없습니다.";
    }
    if (status === 0) {
        return dashboardFallbackMessage("error", status);
    }
    return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}
export function normalizeCreateUserPayload(input) {
    const payload = {
        login_id: input.loginId.trim(),
        username: input.username.trim(),
        password: input.password,
        role: input.role === "ADMIN" ? "ADMIN" : "USER",
    };
    const department = input.department.trim();
    if (department) {
        payload.department = department;
    }
    return payload;
}
export function normalizeRolePayload(role) {
    return { role: role === "ADMIN" ? "ADMIN" : "USER" };
}
export function normalizeStatusPayload(status) {
    return { status: status === "DISABLED" ? "DISABLED" : "ACTIVE" };
}
