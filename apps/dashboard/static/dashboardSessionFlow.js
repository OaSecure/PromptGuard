export function nextProtectedPageAuthState(phase, status) {
    if (phase === "loading") {
        return {
            contentVisible: false,
            redirectToLogin: false,
            message: "대시보드 세션을 확인하고 있습니다.",
        };
    }
    if (phase === "ready") {
        return {
            contentVisible: true,
            redirectToLogin: false,
            message: "",
        };
    }
    return {
        contentVisible: false,
        redirectToLogin: status === 401 || status === 403,
        message: status === 401 ? "대시보드 로그인이 필요합니다." : "대시보드 접근 권한을 확인할 수 없습니다.",
    };
}
export function shouldRedirectAfterLogout(result) {
    return result === "success";
}
export function authFailureMessagePlacement(status) {
    return {
        target: "page-message",
        role: "alert",
        message: status === 401 || status === 403
            ? "대시보드 권한 또는 보안 토큰을 확인할 수 없습니다. 다시 로그인해 주세요."
            : "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    };
}
export async function runDashboardLogout(handlers) {
    try {
        await handlers.logout();
    }
    catch {
        handlers.showError(authFailureMessagePlacement(403));
        return;
    }
    if (shouldRedirectAfterLogout("success")) {
        handlers.redirectToLogin();
    }
}
export function markProtectedDashboardReady(root) {
    root.classList.remove("dashboard-auth-pending");
}
