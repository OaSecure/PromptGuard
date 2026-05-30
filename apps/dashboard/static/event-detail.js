"use strict";
const riskTitle = {
    all: "전체 이벤트 상세보기",
    critical: "Critical 이벤트 상세보기",
    high: "High 이벤트 상세보기",
    medium: "Medium 이벤트 상세보기"
};
const params = new URLSearchParams(window.location.search);
const selectedRisk = params.get("risk") ?? "all";
const detailTitle = document.querySelector("#detail-title");
if (detailTitle) {
    detailTitle.textContent = riskTitle[selectedRisk] ?? riskTitle.all;
}
if (selectedRisk !== "all") {
    document.querySelectorAll("[data-risk]").forEach((row) => {
        if (row.dataset.risk !== selectedRisk) {
            row.hidden = true;
        }
    });
}
document.querySelectorAll(".board-title-button").forEach((button) => {
    button.addEventListener("click", () => {
        const detailId = button.dataset.detailId;
        const detailRow = detailId ? document.getElementById(detailId) : null;
        const icon = button.querySelector(".toggle-icon");
        if (!detailRow || !icon) {
            return;
        }
        const isOpen = detailRow.style.display === "table-row";
        detailRow.style.display = isOpen ? "none" : "table-row";
        icon.textContent = isOpen ? "＋" : "－";
    });
});
