import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import { markProtectedDashboardReady, runDashboardLogout } from "./dashboardSessionFlow.js";
import { getDashboardCsrfToken, logoutDashboardSession, refreshDashboardCsrf } from "./session.js";
import { deriveUsersScreenState, loadingUsersScreenState, normalizeCreateUserPayload, normalizeRolePayload, normalizeStatusPayload, projectUserTableRows, safeUsersMutationErrorMessage, } from "./usersPageModel.js";
import { buildCreateUserRequest, buildUpdateUserRoleRequest, buildUpdateUserStatusRequest, shouldRedirectUsersScreen, } from "./usersRequestModel.js";
const usersTableBody = requireElement("users-table-body");
const usersMessage = requireElement("users-message");
const createUserForm = requireElement("create-user-form");
const createUserButton = requireElement("create-user-submit");
let isMutating = false;
function requireElement(id) {
    const element = document.getElementById(id);
    if (!element) {
        throw new Error(`Missing users dashboard element: ${id}`);
    }
    return element;
}
function redirectToLogin() {
    window.location.href = "./login.html";
}
function setMessage(text, kind) {
    usersMessage.textContent = text;
    usersMessage.hidden = kind === "ready";
    usersMessage.setAttribute("role", kind === "error" ? "alert" : "status");
    usersMessage.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
}
function setCreateUserPending(nextPending) {
    isMutating = nextPending;
    createUserButton.disabled = nextPending;
    createUserButton.textContent = nextPending ? "생성 중" : "사용자 생성";
}
function showMutationError(error) {
    setMessage(safeUsersMutationErrorMessage(error instanceof DashboardApiError ? error.status : 0), "error");
    if (error instanceof DashboardApiError && shouldRedirectUsersScreen(error.status)) {
        window.setTimeout(redirectToLogin, 700);
    }
}
function createCell(text, className) {
    const cell = document.createElement("td");
    if (className) {
        const badge = document.createElement("span");
        badge.className = className;
        badge.textContent = text;
        cell.append(badge);
    }
    else {
        cell.textContent = text;
    }
    return cell;
}
function createSelectCell(currentValue, values, onCommit) {
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
        if (button.disabled)
            return;
        const previousValue = currentValue;
        button.disabled = true;
        select.disabled = true;
        try {
            await onCommit(select.value);
        }
        catch (error) {
            select.value = previousValue;
            showMutationError(error);
        }
        finally {
            button.disabled = false;
            select.disabled = false;
        }
    });
    wrapper.append(select, button);
    cell.append(wrapper);
    return cell;
}
function renderUsers(users) {
    markProtectedDashboardReady(document.body);
    const rowViews = projectUserTableRows(users);
    usersTableBody.replaceChildren(...rowViews.map((rowView, index) => {
        const sourceUser = users[index];
        const tr = document.createElement("tr");
        rowView.cells.forEach((cell) => {
            if (cell.key === "role") {
                tr.append(createSelectCell(sourceUser.role, ["USER", "ADMIN"], async (nextRole) => {
                    await updateUserRole(sourceUser.login_id, normalizeRolePayload(nextRole));
                }));
                return;
            }
            if (cell.key === "status") {
                tr.append(createSelectCell(sourceUser.status, ["ACTIVE", "DISABLED"], async (nextStatus) => {
                    await updateUserStatus(sourceUser.login_id, normalizeStatusPayload(nextStatus));
                }));
                return;
            }
            let className;
            if (cell.tone === "role")
                className = "role-badge";
            if (cell.tone === "status")
                className = "user-status";
            if (cell.tone === "count")
                className = "status-badge";
            tr.append(createCell(cell.text, className));
        });
        tr.dataset.loginId = sourceUser.login_id;
        return tr;
    }));
}
async function fetchUsers() {
    return dashboardRequest("/dashboard/users");
}
async function updateUserRole(loginId, payload) {
    const csrfToken = getDashboardCsrfToken() ?? (await refreshDashboardCsrf());
    const request = buildUpdateUserRoleRequest(loginId, payload, csrfToken);
    await dashboardRequest(request.path, request.options);
    await loadUsers();
}
async function updateUserStatus(loginId, payload) {
    const csrfToken = getDashboardCsrfToken() ?? (await refreshDashboardCsrf());
    const request = buildUpdateUserStatusRequest(loginId, payload, csrfToken);
    await dashboardRequest(request.path, request.options);
    await loadUsers();
}
async function createUser(payload) {
    const csrfToken = getDashboardCsrfToken() ?? (await refreshDashboardCsrf());
    const request = buildCreateUserRequest(payload, csrfToken);
    await dashboardRequest(request.path, request.options);
}
async function loadUsers() {
    const loadingState = loadingUsersScreenState();
    setMessage(loadingState.message, loadingState.kind);
    try {
        const users = await fetchUsers();
        renderUsers(users);
        const screenState = deriveUsersScreenState(users, false);
        setMessage(screenState.message, screenState.kind);
    }
    catch (error) {
        if (!(error instanceof DashboardApiError) || !shouldRedirectUsersScreen(error.status)) {
            markProtectedDashboardReady(document.body);
        }
        const screenState = deriveUsersScreenState([], true);
        setMessage(screenState.message, screenState.kind);
        if (error instanceof DashboardApiError && shouldRedirectUsersScreen(error.status)) {
            window.setTimeout(redirectToLogin, 700);
        }
    }
}
createUserForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isMutating)
        return;
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
    }
    catch (error) {
        showMutationError(error);
        const passwordInput = createUserForm.querySelector("input[name='password']");
        if (passwordInput)
            passwordInput.value = "";
    }
    finally {
        setCreateUserPending(false);
    }
});
document.querySelectorAll(".logout-button").forEach((link) => {
    link.addEventListener("click", async (event) => {
        event.preventDefault();
        await runDashboardLogout({
            logout: logoutDashboardSession,
            redirectToLogin,
            showError: (placement) => setMessage(placement.message, "error"),
        });
    });
});
void loadUsers();
