const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file");
const fileNameEl = document.getElementById("file-name");
const errorEl = document.getElementById("error");
const statusEl = document.getElementById("status");
const issuesEl = document.getElementById("issues");
const exportRow = document.getElementById("export-row");
const resultPanel = document.getElementById("result-panel");
const scoreRing = document.getElementById("score-ring");
const heatBlock = document.getElementById("heat-block");
const overlayImg = document.getElementById("overlay-img");

let lastMarkdown = "";
let lastJson = "";
let busy = false;

const CHECK_SHORT = {
  ela: "ELA",
  text_font: "Text/font",
  metadata: "Metadata",
  copy_move: "Copy-move",
  logic: "Logic",
};

function setBusy(isBusy, message = "") {
  busy = isBusy;
  resultPanel.classList.toggle("loading", isBusy);
  statusEl.textContent = message;
  document.querySelectorAll("[data-sample]").forEach((btn) => {
    btn.disabled = isBusy;
  });
}

function renderBars(checks) {
  const target = document.getElementById("result-bars");
  target.innerHTML = checks
    .map((c) => {
      const pct = Math.max(0, Math.min(100, c.score));
      const label = CHECK_SHORT[c.name] || c.label || c.name;
      return `<div class="bar-row">
        <span>${label}</span>
        <div class="track"><div class="fill" style="width:${pct}%"></div></div>
        <strong>${Math.round(c.score)}</strong>
      </div>`;
    })
    .join("");
}

function renderIssues(issues) {
  const countEl = document.getElementById("issue-count");
  if (!issues.length) {
    countEl.textContent = "All clear";
    issuesEl.innerHTML = `<p class="placeholder">No major forensic flags. Still verify through official channels.</p>`;
    return;
  }
  countEl.textContent = `${issues.length} ranked`;
  issuesEl.innerHTML = issues
    .map(
      (issue, idx) => `<article class="issue">
        <div class="issue-top">
          <span class="rank">${idx + 1}</span>
          <span class="sev ${issue.severity}">${issue.severity} · ${issue.check}</span>
        </div>
        <h4>${issue.title}</h4>
        <p>${issue.detail}</p>
        ${issue.evidence ? `<p><code>${issue.evidence}</code></p>` : ""}
      </article>`,
    )
    .join("");
}

function applyResult(data) {
  errorEl.classList.add("hidden");
  const score = Math.round(data.overall_score);
  document.getElementById("result-score").textContent = score;
  document.getElementById("result-verdict").textContent = data.verdict;
  document.getElementById("result-title").textContent = data.file_name.replace(/_/g, " ");
  document.getElementById("result-meta").textContent =
    `${data.width}×${data.height}px · ${data.verdict}`;
  scoreRing.dataset.verdict = data.verdict;
  renderBars(data.checks);
  renderIssues(data.top_issues || []);
  lastMarkdown = data.markdown || "";
  lastJson = data.json_export || "";
  exportRow.classList.remove("hidden");

  if (data.overlay_url) {
    overlayImg.src = data.overlay_url + "?t=" + Date.now();
    heatBlock.classList.remove("hidden");
  } else {
    heatBlock.classList.add("hidden");
  }

  if (String(data.file_name).includes("genuine")) {
    document.getElementById("genuine-score").textContent = String(score);
  }
  if (String(data.file_name).includes("tampered")) {
    document.getElementById("tampered-score").textContent = String(score);
  }
}

async function scan({ file, sample }) {
  if (busy) return;
  setBusy(true, sample ? `Scanning ${sample} sample…` : "Running forensic checks…");
  errorEl.classList.add("hidden");
  try {
    const body = new FormData();
    if (sample) body.append("sample", sample);
    if (file) body.append("file", file);
    const res = await fetch("/api/scan", { method: "POST", body });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Scan failed");
    applyResult(data);
    setBusy(false, "Scan complete");
  } catch (err) {
    errorEl.textContent = err.message || String(err);
    errorEl.classList.remove("hidden");
    setBusy(false, "");
  }
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});

["dragenter", "dragover"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});
["dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  fileNameEl.textContent = file.name;
  fileNameEl.classList.remove("hidden");
  scan({ file });
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  fileNameEl.textContent = file.name;
  fileNameEl.classList.remove("hidden");
  scan({ file });
});

document.querySelectorAll("[data-sample]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const sample = btn.getAttribute("data-sample");
    fileNameEl.textContent = `${sample}_marksheet.jpg`;
    fileNameEl.classList.remove("hidden");
    scan({ sample });
  });
});

function downloadText(filename, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

document.getElementById("dl-md").addEventListener("click", () => {
  if (!lastMarkdown) return;
  downloadText("certificate-doctor-report.md", lastMarkdown, "text/markdown");
});
document.getElementById("dl-json").addEventListener("click", () => {
  if (!lastJson) return;
  downloadText("certificate-doctor-report.json", lastJson, "application/json");
});
