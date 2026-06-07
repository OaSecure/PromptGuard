import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import { getDashboardCsrfToken, logoutDashboardSession, refreshDashboardCsrf } from "./session.js";
import {
  type CreateUserPayload,
  type DashboardUserRow,
  type UpdateRolePayload,
  type UpdateStatusPayload,
  deriveUsersScreenState,
  loadingUsersScreenState,
  normalizeCreateUserPayload,
  normalizeRolePayload,
  normalizeStatusPayload,
  projectUserTableRows,
  safeUsersMutationErrorMessage,
} from "./usersPageModel.js";

const usersTableBody = requireElement<HTMLTableSectionElement>("users-table-body");
const usersMessage = requireElement<HTMLElement>("users-message");
const createUserForm = requireElement<HTMLFormElement>("create-user-form");
const createUserButton = requireElement<HTMLButtonElement>("create-user-submit");

let isMutating = false;

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing users dashboard element: ${id}`);
  }
  return element as T;
}

function redirectToLogin(): void {
  window.location.href = "./login.html";
}

function setMessage(text: string, kind: "loading" | "empty" | "error" | "ready"): void {
  usersMessage.textContent = text;
  usersMessage.hidden = kind === "ready";
  usersMessage.setAttribute("role", kind === "error" ? "alert" : "status");
  usersMessage.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
}

function setCreateUserPending(nextPending: boolean): void {
  isMutating = nextPending;
  createUserButton.disabled = nextPending;
  createUserButton.textContent = nextPending ? "생성 중" : "사용자 생성";
}

function showMutationError(error: unknown): void {
  setMessage(
    safeUsersMutationErrorMessage(error instanceof DashboardApiError ? error.status : 0),
    "error",
  );
  if (error instanceof DashboardApiError && (error.status === 401 || error.status === 403)) {
    window.setTimeout(redirectToLogin, 700);
  }
}

function createCell(text: string, className?: string): HTMLTableCellElement {
  const cell = document.createElement("td");
  if (className) {
    const badge = document.createElement("span");
    badge.className = className;
    badge.textContent = text;
    cell.append(badge);
  } else {
    cell.textContent = text;
  }
  return cell;
}

function createSelectCell<T extends string>(
  currentValue: T,
  values: readonly T[],
  onCommit: (nextValue: T) => Promise<void>,
): HTMLTableCellElement {
  const cell = document.createElement("td");
  const wrapper = document.createElement("div");
  wrapper.className = "users-inline-control";

  const select = document.createElement("select");
  select.className = "users-select";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === currentValue;
    select.append(option);
  });

  const button = document.createElement("button");
  button.type = "button";
  button.className = "users-inline-button";
  button.textContent = "적용";

  button.addEventListener("click", async () => {
    if (button.disabled) return;
    const previousValue = currentValue;
    button.disabled = true;
    select.disabled = true;
    try {
      await onCommit(select.value as T);
    } catch (error) {
      select.value = previousValue;
      showMutationError(error);
    } finally {
      button.disabled = false;
      select.disabled = false;
    }
  });

  wrapper.append(select, button);
  cell.append(wrapper);
  return cell;
}

function renderUsers(users: DashboardUserRow[]): void {
  const rowViews = projectUserTableRows(users);
  usersTableBody.replaceChildren(
    ...rowViews.map((rowView, index) => {
      const sourceUser = users[index];
      const tr = document.createElement("tr");

      rowView.cells.forEach((cell) => {
        if (cell.key === "role") {
          tr.append(
            createSelectCell(sourceUser.role, ["USER", "ADMIN"] as const, async (nextRole) => {
              await updateUserRole(sourceUser.login_id, normalizeRolePayload(nextRole));
            }),
          );
          return;
        }
        if (cell.key === "status") {
          tr.append(
            createSelectCell(sourceUser.status, ["ACTIVE", "DISABLED"] as const, async (nextStatus) => {
              await updateUserStatus(sourceUser.login_id, normalizeStatusPayload(nextStatus));
            }),
          );
          return;
        }

        let className: string | undefined;
        if (cell.tone === "role") className = "role-badge";
        if (cell.tone === "status") className = "user-status";
        if (cell.tone === "count") className = "status-badge";
        tr.append(createCell(cell.text, className));
      });

      tr.dataset.loginId = sourceUser.login_id;
      return tr;
    }),
  );
}

async function fetchUsers(): Promise<DashboardUserRow[]> {
  return dashboardRequest<DashboardUserRow[]>("/dashboard/users");
}

async function updateUserRole(loginId: string, payload: UpdateRolePayload): Promise<void> {
  const csrfToken = getDashboardCsrfToken() ?? (await refreshDashboardCsrf());
  await dashboardRequest<void>(`/dashboard/users/${encodeURIComponent(loginId)}/role`, {
    method: "PATCH",
    csrfToken,
    body: payload,
  });
  await loadUsers();
}

async function updateUserStatus(loginId: string, payload: UpdateStatusPayload): Promise<void> {
  const csrfToken = getDashboardCsrfToken() ?? (await refreshDashboardCsrf());
  await dashboardRequest<void>(`/dashboard/users/${encodeURIComponent(loginId)}/status`, {
    method: "PATCH",
    csrfToken,
    body: payload,
  });
  await loadUsers();
}

async function createUser(payload: CreateUserPayload): Promise<void> {
  const csrfToken = getDashboardCsrfToken() ?? (await refreshDashboardCsrf());
  await dashboardRequest<void>("/dashboard/users", {
    method: "POST",
    csrfToken,
    body: payload,
  });
}

async function loadUsers(): Promise<void> {
  const loadingState = loadingUsersScreenState();
  setMessage(loadingState.message, loadingState.kind);

  try {
    const users = await fetchUsers();
    renderUsers(users);
    const screenState = deriveUsersScreenState(users, false);
    setMessage(screenState.message, screenState.kind);
  } catch (error) {
    const screenState = deriveUsersScreenState([], true);
    setMessage(screenState.message, screenState.kind);
    if (error instanceof DashboardApiError && (error.status === 401 || error.status === 403)) {
      window.setTimeout(redirectToLogin, 700);
    }
  }
}

createUserForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isMutating) return;

  const formData = new FormData(createUserForm);
  const payload = normalizeCreateUserPayload({
    loginId: String(formData.get("login_id") ?? ""),
    username: String(formData.get("username") ?? ""),
    password: String(formData.get("password") ?? ""),
    department: String(formData.get("department") ?? ""),
    role: String(formData.get("role") ?? "USER"),
  });

  if (!payload.login_id || !payload.username || !payload.password) {
    setMessage("로그인 ID, 사용자 이름, 비밀번호를 입력해 주세요.", "error");
    return;
  }

  setCreateUserPending(true);
  try {
    await createUser(payload);
    createUserForm.reset();
    setMessage("사용자를 생성했습니다.", "ready");
    await loadUsers();
  } catch (error) {
    showMutationError(error);
    const passwordInput = createUserForm.querySelector<HTMLInputElement>("input[name='password']");
    if (passwordInput) passwordInput.value = "";
  } finally {
    setCreateUserPending(false);
  }
});

document.querySelectorAll<HTMLAnchorElement>(".logout-button").forEach((link) => {
  link.addEventListener("click", async (event) => {
    event.preventDefault();
    try {
      await logoutDashboardSession();
    } finally {
      redirectToLogin();
    }
  });
});

void loadUsers();
