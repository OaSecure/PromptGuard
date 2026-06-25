import { DashboardApiError } from "./dashboardApi.js";
import { getDashboardSessionMe, loginDashboardSession, refreshDashboardCsrf } from "./session.js";

const loginForm = document.querySelector<HTMLFormElement>("#login-form");
const loginMessage = document.querySelector<HTMLElement>("#login-message");
const loginButton = loginForm?.querySelector<HTMLButtonElement>("button[type='submit']") ?? null;
const overviewPath = "./overview.html";

let submitting = false;

function setMessage(message: string, kind: "status" | "error" | "success" = "status"): void {
  if (!loginMessage) return;
  loginMessage.textContent = message;
  loginMessage.setAttribute("role", kind === "error" ? "alert" : "status");
  loginMessage.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
  loginMessage.dataset.state = kind;
}

function setSubmitting(nextSubmitting: boolean): void {
  submitting = nextSubmitting;
  if (loginButton) {
    loginButton.disabled = nextSubmitting;
    loginButton.textContent = nextSubmitting ? "Signing in..." : "Login";
  }
}

function safeLoginErrorMessage(error: unknown): string {
  if (error instanceof DashboardApiError) {
    if (error.status === 401) return "The ID or password is incorrect.";
    if (error.status === 403) return "Dashboard access or the security token could not be verified. Please try again.";
    if (error.status === 0) return "Cannot connect to the server. Please try again later.";
  }
  return "An error occurred while signing in. Please try again later.";
}

function redirectToOverview(): void {
  window.location.href = overviewPath;
}

async function checkExistingSession(): Promise<void> {
  setMessage("Loading session...");
  try {
    await getDashboardSessionMe();
    setMessage("Session found. Opening dashboard...", "success");
    redirectToOverview();
  } catch {
    // Staying on the login page is the safe fallback for missing or expired sessions.
    setMessage("");
  }
}

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submitting) return;

  const formData = new FormData(loginForm);
  const loginId = String(formData.get("login_id") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!loginId || !password) {
    setMessage("Please enter your ID and password.", "error");
    return;
  }

  setSubmitting(true);

  try {
    setMessage("Preparing secure sign-in...");
    await refreshDashboardCsrf();
    setMessage("Checking your sign-in information.");
    await loginDashboardSession(loginId, password);
    setMessage("Signed in. Opening dashboard...", "success");
    redirectToOverview();
  } catch (error) {
    setMessage(safeLoginErrorMessage(error), "error");
  } finally {
    setSubmitting(false);
  }
});

void checkExistingSession();
