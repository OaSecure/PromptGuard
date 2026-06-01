import { logoutDashboardSession } from "./session.js";
const logoutLinks = document.querySelectorAll(".logout-button");
function redirectToLogin() {
    window.location.href = "./login.html";
}
logoutLinks.forEach((link) => {
    link.addEventListener("click", async (event) => {
        event.preventDefault();
        try {
            await logoutDashboardSession();
        }
        finally {
            redirectToLogin();
        }
    });
});
