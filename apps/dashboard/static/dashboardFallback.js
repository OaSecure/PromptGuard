export function dashboardFallbackMessage(kind, status) {
    if (kind === "loading")
        return "데이터를 불러오는 중입니다.";
    if (kind === "empty")
        return "표시할 데이터가 없습니다.";
    if (kind === "ready")
        return "";
    if (status === 401 || status === 403)
        return "대시보드 로그인이 필요합니다.";
    if (status === 0)
        return "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
    return "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}
export function dashboardFallbackRole(kind) {
    return kind === "error" ? "alert" : "status";
}
export function dashboardFallbackState(kind, options = {}) {
    void options.detail;
    const role = dashboardFallbackRole(kind);
    return {
        kind,
        message: dashboardFallbackMessage(kind, options.status),
        role,
        ariaLive: role === "alert" ? "assertive" : "polite",
    };
}
