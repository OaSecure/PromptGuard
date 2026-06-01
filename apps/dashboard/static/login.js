import { DashboardApiError } from "./dashboardApi.js";
import { getDashboardSessionMe, loginDashboardSession, refreshDashboardCsrf } from "./session.js";
const loginForm = document.querySelector("#login-form");
const loginMessage = document.querySelector("#login-message");
const loginButton = loginForm?.querySelector("button[type='submit']") ?? null;
const overviewPath = "./overview.html";
let submitting = false;
function setMessage(message, kind = "status") {
    if (!loginMessage)
        return;
    loginMessage.textContent = message;
    loginMessage.setAttribute("role", kind === "error" ? "alert" : "status");
    loginMessage.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
}
function setSubmitting(nextSubmitting) {
    submitting = nextSubmitting;
    if (loginButton) {
        loginButton.disabled = nextSubmitting;
        loginButton.textContent = nextSubmitting ? "로그인 중" : "로그인";
    }
}
function safeLoginErrorMessage(error) {
    if (error instanceof DashboardApiError) {
        if (error.status === 401)
            return "아이디 또는 비밀번호가 올바르지 않습니다.";
        if (error.status === 403)
            return "대시보드 로그인 권한 또는 보안 토큰을 확인할 수 없습니다. 다시 시도해 주세요.";
        if (error.status === 0)
            return "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
    }
    return "로그인 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
}
function redirectToOverview() {
    window.location.href = overviewPath;
}
async function checkExistingSession() {
    try {
        await getDashboardSessionMe();
        redirectToOverview();
    }
    catch {
        // Staying on the login page is the safe fallback for missing or expired sessions.
    }
}
loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitting)
        return;
    const formData = new FormData(loginForm);
    const loginId = String(formData.get("login_id") ?? "").trim();
    const password = String(formData.get("password") ?? "");
    if (!loginId || !password) {
        setMessage("아이디와 비밀번호를 입력해 주세요.", "error");
        return;
    }
    setSubmitting(true);
    setMessage("로그인 정보를 확인하고 있습니다.");
    try {
        await refreshDashboardCsrf();
        await loginDashboardSession(loginId, password);
        redirectToOverview();
    }
    catch (error) {
        setMessage(safeLoginErrorMessage(error), "error");
    }
    finally {
        setSubmitting(false);
    }
});
void checkExistingSession();
