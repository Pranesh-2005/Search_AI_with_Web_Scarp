import { Client } from "https://cdn.jsdelivr.net/npm/@gradio/client/dist/index.min.js";

let currentMode = "quick";
const client = await Client.connect("https://praneshjs-aisearchonlyapp.hf.space/");

// Mode selector
document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
    console.log(`Mode changed to: ${currentMode}`);
  });
});

// Search handlers
document.getElementById("searchBtn").addEventListener("click", performSearch);
document.getElementById("question").addEventListener("keypress", (e) => {
  if (e.key === "Enter") performSearch();
});

async function performSearch() {
  const question = document.getElementById("question").value.trim();
  if (!question) return showStatus("Please enter a question", "error");

  const searchBtn = document.getElementById("searchBtn");
  const loading = document.getElementById("loading");
  const results = document.getElementById("results");
  const loadingText = document.getElementById("loadingText");

  searchBtn.disabled = true;
  loading.style.display = "block";
  results.innerHTML = "";
  loadingText.textContent = currentMode === "deep" ? "Crawling web pages..." : "Searching...";

  try {
    const result = await client.predict("/search_fn", {
      question: question,
      mode: currentMode,
    });

    const answer = result.data[0];
    const sources = result.data[1];
    displayResults(answer, sources, currentMode);
    showStatus("Search completed successfully!", "success");
  } catch (error) {
    console.error("❌ Error:", error);
    displayError("Network error: " + error.message);
    showStatus("Search failed", "error");
  } finally {
    searchBtn.disabled = false;
    loading.style.display = "none";
  }
}

function displayResults(answer, sources, mode) {
  const results = document.getElementById("results");

  const answerHtml = `
    <div class="answer-card">
      <div class="answer-title">✨ Answer (${mode} search):</div>
      <div class="answer-content">${formatAnswer(answer)}</div>
    </div>
  `;

  const sourcesHtml = sources && sources.length > 0
    ? `
      <div class="sources">
        <div class="sources-title">📚 Sources (${sources.length}):</div>
        ${sources.map((src, i) => `
          <div class="source-item">
            <div class="source-title">${i + 1}. ${src.title || "Untitled"}</div>
            <a href="${src.url}" target="_blank" class="source-url">${src.url}</a>
            ${src.snippet ? `<div style="margin-top: 5px; font-size: 0.9em; color: #666;">${src.snippet.substring(0,150)}...</div>` : ""}
          </div>
        `).join("")}
      </div>
    `
    : '<div class="sources"><div class="sources-title">No sources available</div></div>';

  results.innerHTML = answerHtml + sourcesHtml;
}

function displayError(message) {
  document.getElementById("results").innerHTML = `<div class="error">${message}</div>`;
}

function formatAnswer(answer) {
  return answer
    .replace(/\n/g, "<br>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>");
}

function showStatus(message, type) {
  const existing = document.querySelector(".status-indicator");
  if (existing) existing.remove();

  const statusDiv = document.createElement("div");
  statusDiv.className = `status-indicator status-${type}`;
  statusDiv.textContent = message;
  document.body.appendChild(statusDiv);

  setTimeout(() => statusDiv.remove(), 3000);
}

console.log("🚀 Search Assistant frontend loaded");
