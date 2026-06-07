import type { CreateUserPayload, UpdateRolePayload, UpdateStatusPayload } from "./usersPageModel.js";

type DashboardMutationRequest<TBody> = {
  path: string;
  options: {
    method: "POST" | "PATCH";
    csrfToken: string;
    body: TBody;
  };
};

export function buildCreateUserRequest(
  payload: CreateUserPayload,
  csrfToken: string,
): DashboardMutationRequest<CreateUserPayload> {
  return {
    path: "/dashboard/users",
    options: {
      method: "POST",
      csrfToken,
      body: payload,
    },
  };
}

export function buildUpdateUserRoleRequest(
  loginId: string,
  payload: UpdateRolePayload,
  csrfToken: string,
): DashboardMutationRequest<UpdateRolePayload> {
  return {
    path: `/dashboard/users/${encodeURIComponent(loginId)}/role`,
    options: {
      method: "PATCH",
      csrfToken,
      body: payload,
    },
  };
}

export function buildUpdateUserStatusRequest(
  loginId: string,
  payload: UpdateStatusPayload,
  csrfToken: string,
): DashboardMutationRequest<UpdateStatusPayload> {
  return {
    path: `/dashboard/users/${encodeURIComponent(loginId)}/status`,
    options: {
      method: "PATCH",
      csrfToken,
      body: payload,
    },
  };
}

export function shouldRedirectUsersScreen(status: number): boolean {
  return status === 401 || status === 403;
}
