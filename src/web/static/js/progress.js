/**
 * src/web/static/js/progress.js
 *
 * Connects to the SSE endpoint for a prediction and updates the UI:
 * - Progress bar percentage
 * - Step list icons and states (pending / active / done)
 * - Narrative message area
 * - Auto-redirect to results on completion
 * - Error display on failure
 *
 * SSE endpoint: GET /api/v1/predictions/{id}/stream
 * Event format: { stage, message, progress, detail, elapsed_ms, cost_usd }
 */

(function () {
  "use strict";

  // --- Read config from embedded JSON ---
  var configEl = document.getElementById("progress-config");
  if (!configEl) return;

  var config;
  try {
    config = JSON.parse(configEl.textContent);
  } catch (err) {
    return;
  }

  var predictionId = config.predictionId;
  if (!predictionId) return;

  // --- DOM references ---
  var progressBar = document.getElementById("progress-bar");
  var progressPercent = document.getElementById("progress-percent");
  var progressElapsed = document.getElementById("progress-elapsed");
  var stepList = document.getElementById("step-list");
  var narrativeArea = document.getElementById("narrative-area");
  var narrativeMessage = document.getElementById("narrative-message");
  var narrativeAreaMobile = document.getElementById("narrative-area-mobile");
  var narrativeMessageMobile = document.getElementById("narrative-message-mobile");
  var errorSection = document.getElementById("error-section");
  var errorMessage = document.getElementById("error-message");

  // --- Ordered stage list (matches the <li> data-stage attributes) ---
  var STAGES = [
    "collection",
    "event_identification",
    "trajectory",
    "delphi_r1",
    "delphi_r2",
    "consensus",
    "framing",
    "generation",
    "quality_gate",
  ];

  // Unicode constants for step icons (avoids inline HTML injection)
  var ICON_PENDING = "\u25CB";   // ○
  var ICON_ACTIVE = "\u25CF";    // ●
  var ICON_DONE = "\u2713";      // ✓

  // Track which stage was last active, so we can mark it as "done"
  // when a new stage begins.
  var lastActiveStage = null;
  var stageStartTimes = {};

  // --- Connect to SSE ---
  var sseUrl = "/api/v1/predictions/" + predictionId + "/stream";
  var source = new EventSource(sseUrl);

  source.addEventListener("progress", function (e) {
    var data;
    try {
      data = JSON.parse(e.data);
    } catch (err) {
      return;
    }

    handleProgressEvent(data);
  });

  // Handle generic message events (fallback if server sends unnamed events)
  source.onmessage = function (e) {
    var data;
    try {
      data = JSON.parse(e.data);
    } catch (err) {
      return;
    }

    handleProgressEvent(data);
  };

  source.onerror = function () {
    // EventSource auto-reconnects on transient errors.
    // If the server has closed the connection permanently,
    // check if we're already done.
    if (source.readyState === EventSource.CLOSED) {
      // Poll the prediction status once to decide what to show
      pollStatus();
    }
  };

  /**
   * Process a single SSE progress event.
   * @param {Object} data - Parsed SSE event payload.
   */
  function handleProgressEvent(data) {
    var stage = data.stage;
    var message = data.message || "";
    var progress = data.progress || 0;
    var elapsedMs = data.elapsed_ms || 0;

    // --- Update progress bar ---
    var pct = Math.round(progress * 100);
    progressBar.value = pct;
    progressPercent.textContent = pct + "%";

    // --- Update elapsed time ---
    if (elapsedMs > 0) {
      progressElapsed.textContent = formatDuration(elapsedMs);
    }

    // --- Handle terminal states ---
    if (stage === "completed") {
      markAllDone();
      source.close();
      showNarrative("Прогноз готов!");
      // Small delay so user sees 100% before redirect
      setTimeout(function () {
        window.location.href = "/results/" + predictionId;
      }, 1500);
      return;
    }

    if (stage === "failed") {
      source.close();
      showError(message || "Произошла ошибка при выполнении прогноза");
      return;
    }

    // --- Update step list ---
    updateSteps(stage, elapsedMs);

    // --- Update narrative ---
    if (message && data.detail) {
      showNarrative(data.detail);
    } else if (message) {
      showNarrative(message);
    }

    // --- Update per-step inline detail ---
    if (data.detail && stage) {
      var activeLi = stepList.querySelector('[data-stage="' + stage + '"]');
      if (activeLi) {
        var detailEl = activeLi.querySelector(".fn-step-detail");
        if (detailEl) detailEl.textContent = data.detail;
      }
    }
  }

  /**
   * Update step list: mark previous as done, current as active.
   * @param {string} currentStage - The stage identifier.
   * @param {number} elapsedMs - Total elapsed time.
   */
  function updateSteps(currentStage, elapsedMs) {
    var stageIndex = STAGES.indexOf(currentStage);
    if (stageIndex === -1) return; // Unknown stage (queued, etc.)

    // Record start time for the current stage
    if (!stageStartTimes[currentStage]) {
      stageStartTimes[currentStage] = elapsedMs;
    }

    // If we moved to a new stage, mark the previous one as done
    if (lastActiveStage && lastActiveStage !== currentStage) {
      var prevLi = stepList.querySelector(
        '[data-stage="' + lastActiveStage + '"]'
      );
      if (prevLi) {
        markStepDone(prevLi, lastActiveStage, elapsedMs);
      }
    }

    // Mark all stages before the current one as done
    for (var i = 0; i < stageIndex; i++) {
      var li = stepList.querySelector('[data-stage="' + STAGES[i] + '"]');
      if (li && !li.classList.contains("fn-step--done")) {
        markStepDone(li, STAGES[i], elapsedMs);
      }
    }

    // Mark current stage as active
    var currentLi = stepList.querySelector(
      '[data-stage="' + currentStage + '"]'
    );
    if (currentLi && !currentLi.classList.contains("fn-step--done")) {
      currentLi.className = "fn-step fn-step--active";
      currentLi.querySelector(".fn-step-icon").textContent = ICON_ACTIVE;
    }

    lastActiveStage = currentStage;
  }

  /**
   * Mark a step <li> as done.
   * @param {HTMLElement} li
   * @param {string} stageName
   * @param {number} currentElapsedMs
   */
  function markStepDone(li, stageName, currentElapsedMs) {
    li.className = "fn-step fn-step--done";
    li.querySelector(".fn-step-icon").textContent = ICON_DONE;

    // Clear per-step detail on completion
    var detailEl = li.querySelector(".fn-step-detail");
    if (detailEl) detailEl.textContent = "";

    // Calculate and display duration for this stage
    var startMs = stageStartTimes[stageName];
    if (startMs !== undefined) {
      var durationMs = currentElapsedMs - startMs;
      var durationEl = li.querySelector(".fn-step-duration");
      if (durationEl && durationMs > 0) {
        durationEl.textContent = formatDuration(durationMs);
      }
    }
  }

  /**
   * Mark all steps as done (called on "completed").
   */
  function markAllDone() {
    progressBar.value = 100;
    progressPercent.textContent = "100%";

    var items = stepList.querySelectorAll(".fn-step");
    items.forEach(function (li) {
      li.className = "fn-step fn-step--done";
      li.querySelector(".fn-step-icon").textContent = ICON_DONE;
    });
  }

  /**
   * Show the narrative message area.
   * @param {string} text
   */
  function showNarrative(text) {
    narrativeMessage.textContent = text;
    narrativeArea.hidden = false;
    // Mirror to mobile narrative
    if (narrativeMessageMobile) {
      narrativeMessageMobile.textContent = text;
      narrativeAreaMobile.hidden = false;
    }
  }

  /**
   * Show the error section.
   * @param {string} text
   */
  function showError(text) {
    errorMessage.textContent = text;
    errorSection.hidden = false;

    // Hide the progress elements
    progressBar.hidden = true;
    document.querySelector(".fn-progress-meta").hidden = true;
  }

  /**
   * Format milliseconds into human-readable Russian duration.
   * @param {number} ms
   * @returns {string}
   */
  function formatDuration(ms) {
    var totalSec = Math.round(ms / 1000);
    if (totalSec < 60) {
      return totalSec + " сек.";
    }
    var min = Math.floor(totalSec / 60);
    var sec = totalSec % 60;
    return min + " мин. " + sec + " сек.";
  }

  /**
   * Fallback: poll prediction status via REST if SSE drops.
   */
  function pollStatus() {
    fetch("/api/v1/predictions/" + predictionId)
      .then(function (resp) {
        if (!resp.ok) throw new Error("Poll failed");
        return resp.json();
      })
      .then(function (data) {
        if (data.status === "completed") {
          window.location.href = "/results/" + predictionId;
        } else if (data.status === "failed") {
          showError(data.error || "Прогноз завершился с ошибкой");
        } else {
          // Still in progress -- try reconnecting SSE after a delay
          setTimeout(function () {
            window.location.reload();
          }, 5000);
        }
      })
      .catch(function () {
        showError("Потеряно соединение с сервером. Обновите страницу.");
      });
  }
})();
