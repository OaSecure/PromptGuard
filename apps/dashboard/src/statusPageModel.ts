type StatusValue = "healthy" | "degraded" | "unhealthy" | "unknown";

export type DashboardStatus = {
  status: StatusValue;
  last_checked: string;
  api_status: StatusValue;
  postgres_status: StatusValue;
  migration_status: StatusValue;
  filter_rules_status: StatusValue;
};

export type StatusExtensionSetupPlan = {
  title: string;
  description: string;
  settings: {
    label: string;
    value: string;
    description: string;
  }[];
  steps: string[];
};

export type StatusRenderPlan = {
  payload: DashboardStatus;
  extensionSetup: StatusExtensionSetupPlan;
};

const LOCAL_DASHBOARD_PORT = "3000";
const LOCAL_API_PORT = "8000";

function fallbackApiOrigin(): string {
  return "http://localhost:8000";
}

function isLocalHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

export function inferExtensionApiOrigin(dashboardOrigin?: string): string {
  if (!dashboardOrigin) return fallbackApiOrigin();
  try {
    const url = new URL(dashboardOrigin);
    if (isLocalHost(url.hostname) && url.port === LOCAL_DASHBOARD_PORT) {
      url.port = LOCAL_API_PORT;
      return url.origin;
    }
    return url.origin;
  } catch {
    return fallbackApiOrigin();
  }
}

export function extensionSetupPlan(dashboardOrigin?: string): StatusExtensionSetupPlan {
  const apiOrigin = inferExtensionApiOrigin(dashboardOrigin);
  return {
    title: "Chrome 확장프로그램 연동",
    description: "확장프로그램 옵션 화면에 입력할 로컬 서버 연결값입니다.",
    settings: [
      {
        label: "API URL",
        value: apiOrigin,
        description: "Chrome 확장프로그램이 이 주소에 /auth/login, /config/extension, /prompts/analyze 요청을 보냅니다. 서버 배포자는 사용자 브라우저에서 접근 가능한 백엔드 API 주소를 알려줘야 합니다.",
      },
      {
        label: "Mock API",
        value: "끔",
        description: "Mock API mode 체크를 해제해야 실제 PromptGuard 서버로 요청합니다.",
      },
      {
        label: "Login ID",
        value: "대시보드에서 생성한 사용자 ID 또는 로컬 기본 관리자 ID admin",
        description: "운영 환경에서는 사용자별 계정을 사용합니다.",
      },
      {
        label: "Password",
        value: "해당 계정의 비밀번호",
        description: "서버 상태 화면은 비밀번호 값을 표시하지 않습니다.",
      },
    ],
    steps: [
      "서버 배포자는 Chrome 확장프로그램 사용자가 접속할 수 있는 백엔드 API origin을 확인합니다.",
      "포트포워딩을 쓰면 내부 컨테이너 주소가 아니라 외부로 열린 host/IP/domain과 포트를 API URL로 안내합니다.",
      "옵션에서 Save를 눌러 API URL과 Mock API 설정을 저장합니다.",
      "Login ID와 Password로 확장프로그램 로그인을 실행합니다.",
      "Sync config를 눌러 서버의 확장 설정을 가져옵니다.",
      "이후 브라우저 입력창에서 Allow/Warn/Mask/Block 동작을 확인합니다.",
    ],
  };
}

export function renderStatusPlan(payload: DashboardStatus, dashboardOrigin?: string): StatusRenderPlan {
  return {
    payload,
    extensionSetup: extensionSetupPlan(dashboardOrigin),
  };
}
