const overviewStats = [
  { label: "Total events", value: 128 },
  { label: "Warned", value: 17, action: "Warned" },
  { label: "Masked", value: 38, action: "Masked" },
  { label: "Blocked", value: 12, action: "Blocked" }
];

const userSummaries = [
  { name: "admin", department: "Security", eventCount: 32, topSignal: "Secret", lastEventAt: "2026-05-26" },
  { name: "user01", department: "Sales", eventCount: 28, topSignal: "Contract", lastEventAt: "2026-05-26" },
  { name: "user02", department: "Ops", eventCount: 21, topSignal: "PII", lastEventAt: "2026-05-25" }
];

const actionTotals = {
  Allowed: 61,
  Warned: 17,
  Masked: 38,
  Blocked: 12
};

const app = document.querySelector("#app");

if (!app) {
  throw new Error("Dashboard root element is missing.");
}

function statCard(stat) {
  const actionClass = stat.action ? ` stat-card--${stat.action.toLowerCase()}` : "";
  return `
    <article class="stat-card${actionClass}">
      <span>${stat.label}</span>
      <strong>${stat.value}</strong>
    </article>
  `;
}

function actionBar([action, total]) {
  const max = Math.max(...Object.values(actionTotals));
  const width = Math.max(8, Math.round((total / max) * 100));

  return `
    <li class="action-row">
      <span>${action}</span>
      <div class="bar" aria-hidden="true"><i style="width: ${width}%"></i></div>
      <strong>${total}</strong>
    </li>
  `;
}

function userRow(user) {
  return `
    <tr>
      <td>${user.name}</td>
      <td>${user.department}</td>
      <td>${user.topSignal}</td>
      <td>${user.eventCount}</td>
      <td>${user.lastEventAt}</td>
    </tr>
  `;
}

app.innerHTML = `
  <main class="shell">
    <aside class="sidebar" aria-label="Dashboard sections">
      <div class="brand">PromptGuard</div>
      <nav>
        <a aria-current="page" href="#overview">Overview</a>
        <a href="#events">Events</a>
        <a href="#users">Users</a>
        <a href="#filters">Filters</a>
        <a href="#status">Status</a>
      </nav>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div>
          <p>ADMIN dashboard</p>
          <h1>Overview</h1>
        </div>
        <button type="button">Log out</button>
      </header>

      <section class="stats" aria-label="Event summary">
        ${overviewStats.map(statCard).join("")}
      </section>

      <section class="grid">
        <article class="panel">
          <h2>Action Distribution</h2>
          <ol class="action-list">
            ${Object.entries(actionTotals).map(actionBar).join("")}
          </ol>
        </article>

        <article class="panel">
          <h2>Server Status</h2>
          <div class="status-line">
            <span class="status-dot"></span>
            <strong>Ready for dashboard API integration</strong>
          </div>
          <p class="muted">Only metadata summaries are rendered in this scaffold.</p>
        </article>
      </section>

      <section class="panel">
        <h2>User Event Summary</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Department</th>
                <th>Top signal</th>
                <th>Events</th>
                <th>Last event</th>
              </tr>
            </thead>
            <tbody>${userSummaries.map(userRow).join("")}</tbody>
          </table>
        </div>
      </section>
    </section>
  </main>
`;
