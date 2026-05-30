"use strict";
const loginForm = document.querySelector("#login-form");
const loginMessage = document.querySelector("#login-message");
loginForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(loginForm);
    const username = String(formData.get("username") ?? "");
    const password = String(formData.get("password") ?? "");
    if (username === "admin" && password === "1234") {
        window.location.href = "./admin.html";
        return;
    }
    if (loginMessage) {
        loginMessage.textContent = "아이디 또는 비밀번호가 올바르지 않습니다.";
    }
});
