"use strict";
const loginForm = document.querySelector("#login-form");
const loginMessage = document.querySelector("#login-message");
// Temporary static-dashboard mock until real dashboard session auth is wired.
const MOCK_LOGIN = {
    username: "admin",
    password: "1234",
};
function isMockLogin(username, password) {
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
