const loginForm = document.querySelector<HTMLFormElement>("#login-form");
const loginMessage = document.querySelector<HTMLElement>("#login-message");

// Temporary static-dashboard mock until real dashboard session auth is wired.
const MOCK_LOGIN = {
  username: "admin",
  password: "1234",
} as const;

function isMockLogin(username: string, password: string): boolean {
  return username === MOCK_LOGIN.username && password === MOCK_LOGIN.password;
}

loginForm?.addEventListener("submit", (event) => {
  event.preventDefault();

  const formData = new FormData(loginForm);
  const username = String(formData.get("username") ?? "");
  const password = String(formData.get("password") ?? "");

  if (isMockLogin(username, password)) {
    window.location.href = "./admin.html";
    return;
  }

  if (loginMessage) {
    loginMessage.textContent = "아이디 또는 비밀번호가 올바르지 않습니다.";
  }
});
