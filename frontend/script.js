let currentMode = "quick"

// Mode selector
document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"))
    btn.classList.add("active")
    currentMode = btn.dataset.mode
    console.log(`Mode changed to: ${currentMode}`)
  })
})

// Search functionality
document.getElementById("searchBtn").addEventListener("click", performSearch)
document.getElementById("question").addEventListener("keypress", (e) => {
  if (e.key === "Enter") performSearch()
})

async function performSearch() {
  const question = document.getElementById("question").value.trim()
  if (!question) {
    showStatus("Please enter a question", "error")
    return
  }

  const searchBtn = document.getElementById("searchBtn")
  const loading = document.getElementById("loading")
  const results = document.getElementById("results")
  const loadingText = document.getElementById("loadingText")

  // Show loading
  searchBtn.disabled = true
  loading.style.display = "block"
  results.innerHTML = ""

  loadingText.textContent = currentMode === "deep" ? "Crawling web pages..." : "Searching..."

  const requestData = {
    question: question,
    mode: currentMode,
  }

  console.log("🔍 Sending search request:", requestData)

  try {
    const response = await fetch("https://searaibackend.onrender.com/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(requestData),
    })

    const data = await response.json()

    console.log("📋 Received response:", data)

    if (response.ok && data.status === "success") {
      displayResults(data)
      showStatus("Search completed successfully!", "success")
    } else {
      const errorMsg = data.detail || data.answer || "An error occurred"
      displayError(errorMsg)
      showStatus("Search failed", "error")
    }
  } catch (error) {
    console.error("❌ Network error:", error)
    displayError("Network error: " + error.message)
    showStatus("Network error", "error")
  } finally {
    searchBtn.disabled = false
    loading.style.display = "none"
  }
}

function displayResults(data) {
  const results = document.getElementById("results")

  console.log("📄 Displaying results for mode:", data.mode)

  const answerHtml = `
        <div class="answer-card">
            <div class="answer-title">✨ Answer (${data.mode} search):</div>
            <div class="answer-content">${formatAnswer(data.answer)}</div>
        </div>
    `

  const sourcesHtml =
    data.sources && data.sources.length > 0
      ? `
        <div class="sources">
            <div class="sources-title">📚 Sources (${data.sources.length}):</div>
            ${data.sources
              .map(
                (source, index) => `
                <div class="source-item">
                    <div class="source-title">${index + 1}. ${source.title || "Untitled"}</div>
                    <a href="${source.url}" target="_blank" class="source-url">${source.url}</a>
                    ${source.snippet ? `<div style="margin-top: 5px; font-size: 0.9em; color: #666;">${source.snippet.substring(0, 150)}...</div>` : ""}
                </div>
            `,
              )
              .join("")}
        </div>
    `
      : '<div class="sources"><div class="sources-title">No sources available</div></div>'

  results.innerHTML = answerHtml + sourcesHtml
}

function displayError(message) {
  const results = document.getElementById("results")
  results.innerHTML = `<div class="error">❌ Error: ${message}</div>`
}

function formatAnswer(answer) {
  // Convert newlines to <br> and preserve formatting
  return answer
    .replace(/\n/g, "<br>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
}

function showStatus(message, type) {
  // Remove existing status indicators
  const existingStatus = document.querySelector(".status-indicator")
  if (existingStatus) {
    existingStatus.remove()
  }

  // Create new status indicator
  const statusDiv = document.createElement("div")
  statusDiv.className = `status-indicator status-${type}`
  statusDiv.textContent = message
  document.body.appendChild(statusDiv)

  // Auto remove after 3 seconds
  setTimeout(() => {
    statusDiv.remove()
  }, 3000)

  console.log(`📢 Status: ${message} (${type})`)
}

// Log when script loads
console.log("🚀 Search Assistant frontend loaded")
