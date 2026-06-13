type StatusValue = "healthy" | "degraded" | "unhealthy" | "unknown";

export type DashboardStatus = {
  status: StatusValue;
  last_checked: string;
  api_status: StatusValue;
  postgres_status: StatusValue;
  migration_status: StatusValue;
  filter_rules_status: StatusValue;
  extension_connection: ExtensionConnectionInfo;
};

export type ExtensionConnectionInfo = {
  internal_api_origins: string[];
  excluded_internal_api_origins: string[];
  admin_local_api_origin: string;
  external_api_origin: string | null;
  api_port: string;
};

export type StatusExtensionSetupPlan = {
  title: string;
  description: string;
  connectionCards: {
    label: string;
    value: string;
    description: string;
  }[];
  helpSections: {
    title: string;
    steps: string[];
  }[];
  urlBuilder: {
    apiPort: string;
    excludedOrigins: string[];
  };
};

export type StatusRenderPlan = {
  payload: DashboardStatus;
  extensionSetup: StatusExtensionSetupPlan;
};

function internalOriginValue(connection: ExtensionConnectionInfo): string {
  if (connection.internal_api_origins.length === 0) {
    return "서버 내부망 IP를 확인할 수 없습니다. 아래 확인 방법을 따라 서버 PC의 IPv4 주소를 확인하세요.";
  }
  return connection.internal_api_origins.join(", ");
}

function externalOriginValue(connection: ExtensionConnectionInfo): string {
  if (connection.external_api_origin) {
    return connection.external_api_origin;
  }
  return "자동 감지 안 됨 - 포트포워딩 또는 도메인 설정 후 확인 필요";
}

function externalOriginDescription(connection: ExtensionConnectionInfo): string {
  if (connection.external_api_origin) {
    return "자동 감지됨. 외부에서 접속할 Chrome 확장프로그램 사용자가 API URL에 입력할 주소입니다.";
  }
  return "자동으로 확인하지 못했습니다. 외부 접속이 필요하면 API URL 확인 방법을 열어 외부 주소 확인 절차를 진행하세요.";
}

function dockerBridgeNotice(connection: ExtensionConnectionInfo): string[] {
  if (connection.excluded_internal_api_origins.length === 0) {
    return [];
  }
  return [
    `컨테이너 내부 주소는 제외됨: ${connection.excluded_internal_api_origins.join(", ")}`,
    "이 주소는 Docker 내부 네트워크용이라 Chrome 확장프로그램 API URL로 사용하지 않습니다.",
  ];
}

function parsePort(value: string): number | null {
  if (!/^[0-9]+$/.test(value.trim())) {
    return null;
  }
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return null;
  }
  return port;
}

function normalizeIpv4(value: string): string | null {
  const trimmed = value.trim();
  const parts = trimmed.split(".");
  if (parts.length !== 4 || trimmed.toLowerCase() === "localhost") {
    return null;
  }
  for (const part of parts) {
    if (!/^[0-9]+$/.test(part)) {
      return null;
    }
    const octet = Number(part);
    if (!Number.isInteger(octet) || octet < 0 || octet > 255) {
      return null;
    }
  }
  return trimmed;
}

function normalizeHost(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed || /\s/.test(trimmed)) {
    return null;
  }
  try {
    const parsed = new URL(trimmed.includes("://") ? trimmed : `http://${trimmed}`);
    if (!parsed.hostname || parsed.username || parsed.password) {
      return null;
    }
    return parsed.hostname;
  } catch {
    return null;
  }
}

export function buildLanApiOrigin(rawIp: string, apiPort: string): string | null {
  const ip = normalizeIpv4(rawIp);
  const port = parsePort(apiPort);
  if (!ip || port === null) {
    return null;
  }
  return `http://${ip}:${port}`;
}

export function buildExternalApiOrigin(rawHost: string, rawPort: string, useHttps: boolean): string | null {
  const host = normalizeHost(rawHost);
  const port = parsePort(rawPort);
  if (!host || port === null) {
    return null;
  }
  const scheme = useHttps ? "https" : "http";
  const shouldOmitPort = (scheme === "https" && port === 443) || (scheme === "http" && port === 80);
  return shouldOmitPort ? `${scheme}://${host}` : `${scheme}://${host}:${port}`;
}

export function extensionSetupPlan(connection: ExtensionConnectionInfo): StatusExtensionSetupPlan {
  return {
    title: "Chrome 확장프로그램 연동",
    description: "Chrome 확장프로그램 사용자가 백엔드 서버에 연결할 때 입력할 서버 주소와 포트를 확인합니다.",
    connectionCards: [
      {
        label: "내부망 연결 주소",
        value: internalOriginValue(connection),
        description: "같은 공유기 또는 사내망에 있는 Chrome 확장프로그램 사용자가 API URL에 입력할 수 있는 후보입니다.",
      },
      {
        label: "외부/포트포워딩 주소",
        value: externalOriginValue(connection),
        description: externalOriginDescription(connection),
      },
      {
        label: "API 포트",
        value: connection.api_port,
        description: "확장프로그램 요청을 받는 백엔드 포트입니다. 포트포워딩을 쓰면 외부 포트가 다를 수 있습니다.",
      },
    ],
    helpSections: [
      {
        title: "확장프로그램이 서버와 통신하는 방식",
        steps: [
          "Chrome 확장프로그램은 API URL에 적은 주소를 기준으로 /auth/login, /config/extension, /prompts/analyze 요청을 보냅니다.",
          `관리자 로컬 확인용 주소는 ${connection.admin_local_api_origin}입니다. 이 localhost는 서버 관리자 PC에서만 유효하고, 다른 사용자 컴퓨터에서는 통하지 않습니다.`,
          "확장 사용자의 컴퓨터에서 접속 가능한 주소를 확인한 뒤 그 주소를 사용자에게 안내합니다.",
          ...dockerBridgeNotice(connection),
        ],
      },
      {
        title: "Windows에서 내부망 IP 확인",
        steps: [
          "서버 컴퓨터에서 시작 메뉴를 열고 cmd 또는 PowerShell을 실행합니다.",
          "ipconfig 명령을 입력합니다.",
          "현재 연결된 어댑터에서 IPv4 주소를 찾습니다. 보통 192.168.x.x 또는 10.x.x.x 형태입니다.",
          `Chrome 확장프로그램 사용자에게 http://IPv4주소:${connection.api_port} 형식으로 안내합니다.`,
        ],
      },
      {
        title: "macOS에서 내부망 IP 확인",
        steps: [
          "시스템 설정에서 네트워크를 열고 현재 연결된 Wi-Fi 또는 Ethernet의 IP 주소를 확인합니다.",
          "터미널을 쓸 수 있다면 ipconfig getifaddr en0 또는 ifconfig 명령으로 IPv4 주소를 확인합니다.",
          `Chrome 확장프로그램 사용자에게 http://IPv4주소:${connection.api_port} 형식으로 안내합니다.`,
        ],
      },
      {
        title: "Linux에서 내부망 IP 확인",
        steps: [
          "터미널에서 hostname -I 또는 ip addr 명령을 실행합니다.",
          "lo가 아닌 네트워크 장치의 IPv4 주소를 확인합니다.",
          `Chrome 확장프로그램 사용자에게 http://IPv4주소:${connection.api_port} 형식으로 안내합니다.`,
        ],
      },
      {
        title: "내부망 밖에서 쓰는 포트포워딩 확인",
        steps: [
          "공유기 관리자 페이지 또는 클라우드 방화벽 설정에서 외부 포트가 서버 컴퓨터의 내부 IP와 API 포트로 전달되는지 확인합니다.",
          "외부 포트와 내부 포트가 다르면 Chrome 확장프로그램에는 외부 포트를 입력해야 합니다.",
          "도메인을 연결했다면 API URL은 https://도메인 또는 http://도메인:외부포트 형태입니다.",
          "외부 네트워크의 브라우저에서 해당 주소의 /healthz 또는 /readyz가 열리는지 확인합니다.",
        ],
      },
    ],
    urlBuilder: {
      apiPort: connection.api_port,
      excludedOrigins: connection.excluded_internal_api_origins,
    },
  };
}

export function renderStatusPlan(payload: DashboardStatus): StatusRenderPlan {
  return {
    payload,
    extensionSetup: extensionSetupPlan(payload.extension_connection),
  };
}
