import type { AnalyzeResponse } from "../shared/types";

const CONTEXT_RISK_LABELS: Record<string, string> = {
  BULK_SENSITIVE_RECORD_CONTEXT: "대량 민감 기록",
  CONFIDENTIAL_BUSINESS_CONTEXT: "기밀 비즈니스 정보",
  FINANCIAL_IDENTIFIER_CONTEXT: "금융 식별 정보",
  INTERNAL_OPERATION_CONTEXT: "내부 운영 정보",
  PROPRIETARY_TECHNICAL_CONTEXT: "독점 기술 정보",
  SECURITY_CONTROL_CONTEXT: "보안 통제 정보",
  SECRET_CREDENTIAL_CONTEXT: "인증 정보 또는 접근 권한",
  PERSONAL_DATA_CONTEXT: "개인정보",
  BUSINESS_CONFIDENTIAL_CONTEXT: "기밀 비즈니스 정보",
  FINANCIAL_CONTEXT: "금융 또는 상업 조건",
  LEGAL_CONTRACT_CONTEXT: "법무 또는 계약 정보",
  SECURITY_INCIDENT_CONTEXT: "보안 운영 정보",
  CUSTOMER_DATA_CONTEXT: "고객 또는 계정 정보"
};

const DETECTION_LABELS: Record<string, string> = {
  API_SECRET: "API 키 또는 인증 토큰",
  BANK_ACCOUNT: "계좌번호",
  CARD: "카드번호",
  EMAIL: "이메일 주소",
  PAYMENT: "결제 정보",
  PHONE: "전화번호",
  PII: "개인정보",
  RRN: "주민등록번호",
  SECRET: "인증 정보"
};

/** Builds user-facing decision evidence without exposing internal label codes. */
export function safeDecisionEvidence(response: AnalyzeResponse): string[] {
  const evidence: string[] = [];
  if (response.context_risk_evidence && response.context_risk_evidence.status !== "disabled" && response.context_risk_evidence.status !== "no_candidate") {
    const line = contextRiskEvidenceLine(response.context_risk_evidence);
    if (line) {
      evidence.push(line);
    }
  }
  for (const detection of response.detections.slice(0, 3)) {
    evidence.push(`탐지: ${readableDetection(detection)}`);
  }
  for (const item of response.content_unavailable_inputs.slice(0, 3)) {
    evidence.push(`검사 불가: ${readableContentUnavailableReason(item.reason)}`);
  }
  for (const match of response.business_context_matches.slice(0, 2)) {
    evidence.push(`정책 매칭: ${readablePhrase(match.category)}`);
  }
  if (evidence.length === 0 && response.action !== "Allow") {
    evidence.push("검토가 필요합니다.");
  }
  return evidence;
}

type ContextRiskEvidenceView = NonNullable<AnalyzeResponse["context_risk_evidence"]>;

function contextRiskEvidenceLine(evidence: ContextRiskEvidenceView): string | null {
  const labelText = readableLabels(evidence.labels);
  if (evidence.status === "timeout") {
    return "검사 시간이 초과되었습니다. 다시 시도해 주세요.";
  }
  if (evidence.status === "failed") {
    return "검사를 완료하지 못했습니다. 다시 시도해 주세요.";
  }
  if (!labelText) {
    return null;
  }
  const prefix = evidence.status === "verified" ? "탐지" : "주의";
  return `${prefix}: ${labelText}`;
}

function readableLabels(labels: string[]): string {
  const uniqueLabels = labels.map(readableContextLabel).filter((label, index, values) => values.indexOf(label) === index);
  if (uniqueLabels.length <= 3) {
    return uniqueLabels.join(", ");
  }
  return `${uniqueLabels.slice(0, 3).join(", ")} 외 ${uniqueLabels.length - 3}개`;
}

function readableContextLabel(label: string): string {
  return CONTEXT_RISK_LABELS[label] ?? "정책 관련 정보";
}

function readableDetection(detection: AnalyzeResponse["detections"][number]): string {
  return readableDetectionToken(detection.type)
    ?? readableDetectionToken(detection.placeholder)
    ?? readableDetectionToken(detection.detector_id || "")
    ?? readableDetectionToken(detection.category)
    ?? readablePhrase(detection.category || detection.type);
}

function readableContentUnavailableReason(reason: string): string {
  switch (reason) {
    case "unsupported":
      return "지원되지 않는 형식";
    case "oversized":
      return "용량 초과";
    case "metadata_only":
      return "메타데이터만 검사됨";
    case "unavailable":
      return "내용 확인 불가";
    default:
      return readablePhrase(reason || "unavailable");
  }
}

function readablePhrase(value: string): string {
  return value
    .toLowerCase()
    .split(/[_\s-]+/)
    .filter(Boolean)
    .join(" ");
}

function readableDetectionToken(value: string): string | null {
  const normalized = value.trim().toUpperCase().replace(/[\s-]+/g, "_");
  return DETECTION_LABELS[normalized] ?? null;
}
