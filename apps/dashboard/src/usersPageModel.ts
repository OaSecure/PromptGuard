export type DashboardUserRow = {
  login_id: string;
  username: string;
  department: string | null;
  role: "USER" | "ADMIN";
  status: "ACTIVE" | "DISABLED";
  created_at: string;
  last_login_at: string | null;
  last_event_at: string | null;
  event_count: number;
  blocked_count: number;
  masked_count: number;
  warned_count: number;
};

export type CreateUserPayload = {
  login_id: string;
  username: string;
  password: string;
  department?: string | null;
  role: "USER" | "ADMIN";
};

export type UpdateRolePayload = {
  role: "USER" | "ADMIN";
};

export type UpdateStatusPayload = {
  status: "ACTIVE" | "DISABLED";
};

export type UserTableCell = {
  key: string;
  text: string;
  tone?: "default" | "role" | "status" | "count" | "empty";
};

export type UserTableRowView = {
  loginId: string;
  cells: UserTableCell[];
};

export type UsersScreenState =
  | { kind: "loading"; message: string }
  | { kind: "empty"; message: string }
  | { kind: "ready"; message: string }
  | { kind: "error"; message: string };

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
] as const;

type TableColumn = (typeof TABLE_COLUMNS)[number];

const SAFE_EMPTY_VALUE = "-";

function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatDateTime(value: string | null): string {
  if (!value) return SAFE_EMPTY_VALUE;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return SAFE_EMPTY_VALUE;
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function columnText(user: DashboardUserRow, column: TableColumn): string {
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

function columnTone(column: TableColumn): UserTableCell["tone"] {
  if (column === "role") return "role";
  if (column === "status") return "status";
  if (column.endsWith("_count") || column === "event_count") return "count";
  return "default";
}

export function projectUserTableRows(users: DashboardUserRow[]): UserTableRowView[] {
  return users.map((user) => ({
    loginId: user.login_id,
    cells: TABLE_COLUMNS.map((column) => ({
      key: column,
      text: columnText(user, column),
      tone: columnTone(column),
    })),
  }));
}

export function deriveUsersScreenState(users: DashboardUserRow[], hadError: boolean): UsersScreenState {
  if (hadError) {
    return { kind: "error", message: "사용자 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요." };
  }
  if (users.length === 0) {
    return { kind: "empty", message: "등록된 사용자가 없습니다." };
  }
  return { kind: "ready", message: "" };
}

export function loadingUsersScreenState(): UsersScreenState {
  return { kind: "loading", message: "사용자 정보를 불러오는 중입니다." };
}

export function safeUsersMutationErrorMessage(status: number): string {
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
    return "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  }
  return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

export function normalizeCreateUserPayload(input: {
  loginId: string;
  username: string;
  password: string;
  department: string;
  role: string;
}): CreateUserPayload {
  const payload: CreateUserPayload = {
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

export function normalizeRolePayload(role: string): UpdateRolePayload {
  return { role: role === "ADMIN" ? "ADMIN" : "USER" };
}

export function normalizeStatusPayload(status: string): UpdateStatusPayload {
  return { status: status === "DISABLED" ? "DISABLED" : "ACTIVE" };
}
