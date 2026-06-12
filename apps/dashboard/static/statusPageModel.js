export function extensionSetupPlan() {
    return {
        title: "Chrome 확장프로그램 연동",
        description: "대시보드 서버와 확장프로그램을 같은 API 기준으로 연결할 때 확인할 항목입니다.",
        steps: [
            "확장프로그램 옵션에서 API URL을 현재 PromptGuard API 주소로 설정합니다.",
            "Mock 모드는 끄고 실제 API 모드로 전환합니다.",
            "확장프로그램에서 로그인한 뒤 설정 동기화를 실행합니다.",
            "이후 브라우저 입력창에서 Allow/Warn/Mask/Block 동작을 확인합니다.",
        ],
    };
}
export function renderStatusPlan(payload) {
    return {
        payload,
        extensionSetup: extensionSetupPlan(),
    };
}
