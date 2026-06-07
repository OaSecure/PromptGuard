export function buildCreateUserRequest(payload, csrfToken) {
    return {
        path: "/dashboard/users",
        options: {
            method: "POST",
            csrfToken,
            body: payload,
        },
    };
}
export function buildUpdateUserRoleRequest(loginId, payload, csrfToken) {
    return {
        path: `/dashboard/users/${encodeURIComponent(loginId)}/role`,
        options: {
            method: "PATCH",
            csrfToken,
            body: payload,
        },
    };
}
export function buildUpdateUserStatusRequest(loginId, payload, csrfToken) {
    return {
        path: `/dashboard/users/${encodeURIComponent(loginId)}/status`,
        options: {
            method: "PATCH",
            csrfToken,
            body: payload,
        },
    };
}
export function shouldRedirectUsersScreen(status) {
    return status === 401 || status === 403;
}
