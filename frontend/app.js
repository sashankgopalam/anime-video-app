// API_BASE_URL comes from config.js -- "" for same-origin (local dev),
// or a deployed backend URL (e.g. Render) when frontend/backend are split.
const API = window.API_BASE_URL || "";

const LANGUAGE_LABELS = {
  "te-IN": "Telugu",
  "hi-IN": "Hindi",
  "ta-IN": "Tamil",
  "kn-IN": "Kannada",
  "ml-IN": "Malayalam",
  "mr-IN": "Marathi",
  "bn-IN": "Bengali",
  "en-IN": "English (India)",
  "en-US": "English (US)",
  "ja-JP": "Japanese",
};

const titleEl = document.getElementById("title");
const storyEl = document.getElementById("story");
const languageEl = document.getElementById("language");
const maxScenesEl = document.getElementById("maxScenes");
const generateBtn = document.getElementById("generateBtn");
const errorMsg = document.getElementById("errorMsg");

const progressCard = document.getElementById("progressCard");
const progressFill = document.getElementById("progressFill");
const stageText = document.getElementById("stageText");
const sceneCount = document.getElementById("sceneCount");

const resultCard = document.getElementById("resultCard");
const resultVideo = document.getElementById("resultVideo");
const downloadLink = document.getElementById("downloadLink");

let pollTimer = null;

async function loadLanguages() {
  try {
    const res = await fetch(`${API}/api/languages`);
    const data = await res.json();
    const codes = Object.keys(data.languages || {});
    languageEl.innerHTML = codes
      .map((code) => `<option value="${code}">${LANGUAGE_LABELS[code] || code}</option>`)
      .join("");
    languageEl.value = data.default || "te-IN";
  } catch (e) {
    languageEl.innerHTML = `<option value="te-IN">Telugu</option>`;
  }
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.hidden = !msg;
}

function resetPanels() {
  progressCard.hidden = true;
  resultCard.hidden = true;
  showError("");
}

async function startJob() {
  const story = storyEl.value.trim();
  if (!story) {
    showError("Please paste a story or scene description first.");
    return;
  }
  resetPanels();
  generateBtn.disabled = true;
  progressCard.hidden = false;
  progressFill.style.width = "2%";
  stageText.textContent = "Submitting…";

  try {
    const res = await fetch(`${API}/api/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: titleEl.value.trim(),
        story,
        language: languageEl.value,
        max_scenes: Number(maxScenesEl.value) || 10,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to start job");
    pollJob(data.id);
  } catch (e) {
    generateBtn.disabled = false;
    progressCard.hidden = true;
    showError(e.message);
  }
}

function pollJob(jobId) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${API}/api/jobs/${jobId}`);
      const job = await res.json();
      if (!res.ok) throw new Error(job.error || "Job lookup failed");

      progressFill.style.width = `${job.progress || 0}%`;
      stageText.textContent = job.stage || job.status;
      sceneCount.textContent = job.scenes_total
        ? `Scene ${job.scenes_done}/${job.scenes_total}`
        : "";

      if (job.status === "done" && job.video_ready) {
        clearInterval(pollTimer);
        generateBtn.disabled = false;
        progressCard.hidden = true;
        resultCard.hidden = false;
        const videoUrl = `${API}/api/jobs/${jobId}/video`;
        resultVideo.src = videoUrl;
        downloadLink.href = videoUrl;
      } else if (job.status === "error") {
        clearInterval(pollTimer);
        generateBtn.disabled = false;
        progressCard.hidden = true;
        showError(job.error || "Something went wrong generating the video.");
      }
    } catch (e) {
      clearInterval(pollTimer);
      generateBtn.disabled = false;
      showError(e.message);
    }
  }, 1200);
}

generateBtn.addEventListener("click", startJob);
loadLanguages();
