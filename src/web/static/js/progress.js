/**
 * src/web/static/js/progress.js
 *
 * Connects to the SSE endpoint for a prediction and updates the UI:
 * - Progress bar percentage
 * - Step list icons and states (pending / active / done)
 * - Narrative message area
 * - Auto-redirect to results on completion
 * - Error display on failure
 * - State recovery on page refresh (REST fetch before SSE)
 * - Stall detection with user-visible warning
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
  var stallWarning = document.getElementById("stall-warning");
  var stallMessage = document.getElementById("stall-message");

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

  // Progress percentage per stage (mirrors src/schemas/progress.py STAGE_PROGRESS_MAP)
  var STAGE_PROGRESS = {
    collection: 0.05,
    event_identification: 0.20,
    trajectory: 0.30,
    delphi_r1: 0.40,
    delphi_r2: 0.55,
    consensus: 0.70,
    framing: 0.80,
    generation: 0.88,
    quality_gate: 0.95,
  };

  // Unicode constants for step icons (avoids inline HTML injection)
  var ICON_PENDING = "\u25CB";   // ○
  var ICON_ACTIVE = "\u25CF";    // ●
  var ICON_DONE = "\u2713";      // ✓

  // Track which stage was last active, so we can mark it as "done"
  // when a new stage begins.
  var lastActiveStage = null;
  var stageStartTimes = {};

  // Stall detection
  var lastEventTime = Date.now();
  var stallTimerId = null;
  var source = null;

  // --- Entry point: fetch REST state first, then connect SSE ---
  initFromRest();

  /**
   * Fetch current prediction state from REST API, restore UI, then connect SSE.
   */
  function initFromRest() {
    fetch("/api/v1/predictions/" + predictionId, { credentials: "same-origin" })
      .then(function (resp) {
        if (!resp.ok) {
          // Prediction not found or access denied — connect SSE anyway
          connectSSE();
          return null;
        }
        return resp.json();
      })
      .then(function (data) {
        if (!data) return;

        // Terminal states: redirect or show error, no SSE needed
        if (data.status === "completed") {
          window.location.href = "/results/" + predictionId;
          return;
        }

        if (data.status === "failed") {
          showError(data.error_message || "Прогноз завершился с ошибкой");
          return;
        }

        // Restore state from pipeline_steps
        restoreFromPipelineSteps(data);

        // Connect SSE for live updates
        connectSSE();
      })
      .catch(function () {
        // REST failed — still try SSE
        connectSSE();
      });
  }

  /**
   * Restore step list and progress bar from REST response.
   * pipeline_steps[].agent_name = stage name (e.g. "collection", "trajectory")
   * pipeline_steps[].status = "completed" | "failed"
   * pipeline_steps[].duration_ms = stage duration
   */
  function restoreFromPipelineSteps(data) {
    var steps = data.pipeline_steps || [];
    var completedSet = {};
    var durationMap = {};

    for (var i = 0; i < steps.length; i++) {
      var step = steps[i];
      if (step.status === "completed") {
        completedSet[step.agent_name] = true;
        if (step.duration_ms) {
          durationMap[step.agent_name] = step.duration_ms;
        }
      }
    }

    var activeStage = null;
    var isPastPending = data.status !== "pending";

    for (var j = 0; j < STAGES.length; j++) {
      var stageName = STAGES[j];
      var li = stepList.querySelector('[data-stage="' + stageName + '"]');
      if (!li) continue;

      if (completedSet[stageName]) {
        // Mark as done with duration
        li.className = "fn-step fn-step--done";
        li.querySelector(".fn-step-icon").textContent = ICON_DONE;
        if (durationMap[stageName]) {
          var durationEl = li.querySelector(".fn-step-duration");
          if (durationEl) durationEl.textContent = formatDuration(durationMap[stageName]);
        }
      } else if (!activeStage && isPastPending) {
        // First non-completed stage while task is running = active
        activeStage = stageName;
        li.className = "fn-step fn-step--active";
        li.querySelector(".fn-step-icon").textContent = ICON_ACTIVE;
      }
      // else: stays pending (default HTML state)
    }

    // Update progress bar
    if (activeStage && STAGE_PROGRESS[activeStage] !== undefined) {
      var pct = Math.round(STAGE_PROGRESS[activeStage] * 100);
      progressBar.value = pct;
      progressPercent.textContent = pct + "%";
      lastActiveStage = activeStage;
    }
  }

  /**
   * Connect to SSE stream and start stall detection.
   */
  function connectSSE() {
    var sseUrl = "/api/v1/predictions/" + predictionId + "/stream";
    source = new EventSource(sseUrl);

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
        stopStallDetection();
        pollStatus();
      }
    };

    // Start stall detection
    lastEventTime = Date.now();
    startStallDetection();
  }

  /**
   * Process a single SSE progress event.
   * @param {Object} data - Parsed SSE event payload.
   */
  function handleProgressEvent(data) {
    var stage = data.stage;
    var message = data.message || "";
    var elapsedMs = data.elapsed_ms || 0;

    // Reset stall detection on every event
    lastEventTime = Date.now();
    hideStallWarning();

    // --- Update progress bar (only when progress field is present) ---
    if (data.progress !== undefined && data.progress !== null) {
      var pct = Math.round(data.progress * 100);
      progressBar.value = pct;
      progressPercent.textContent = pct + "%";
    }

    // --- Update elapsed time ---
    if (elapsedMs > 0) {
      progressElapsed.textContent = formatDuration(elapsedMs);
    }

    // --- Handle terminal states ---
    if (stage === "completed") {
      markAllDone();
      source.close();
      stopStallDetection();
      showNarrative("Прогноз готов!");
      // Small delay so user sees 100% before redirect
      setTimeout(function () {
        window.location.href = "/results/" + predictionId;
      }, 1500);
      return;
    }

    if (stage === "failed") {
      source.close();
      stopStallDetection();
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

  // --- Stall detection ---

  /**
   * Start interval timer that checks for stalled progress.
   */
  function startStallDetection() {
    if (stallTimerId) return;
    stallTimerId = setInterval(checkStall, 5000);
  }

  /**
   * Stop stall detection timer.
   */
  function stopStallDetection() {
    if (stallTimerId) {
      clearInterval(stallTimerId);
      stallTimerId = null;
    }
    hideStallWarning();
  }

  /**
   * Check if progress has stalled and show appropriate warning.
   */
  function checkStall() {
    // No-op: stall warnings disabled.
    // The info banner in progress.html tells users to expect 30-40 min.
  }

  /**
   * Show the stall warning banner.
   * @param {string} text
   */
  function showStallWarning(text) {
    if (!stallWarning || !stallMessage) return;
    stallMessage.textContent = text;
    stallWarning.hidden = false;
  }

  /**
   * Hide the stall warning banner.
   */
  function hideStallWarning() {
    if (!stallWarning) return;
    stallWarning.hidden = true;
    markActiveStepStalled(false);
  }

  /**
   * Toggle stalled visual on the currently active step.
   * @param {boolean} stalled
   */
  function markActiveStepStalled(stalled) {
    var activeEl = stepList.querySelector(".fn-step--active");
    if (!activeEl) return;
    if (stalled) {
      activeEl.classList.add("fn-step--stalled");
    } else {
      activeEl.classList.remove("fn-step--stalled");
    }
  }

  // --- Utilities ---

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
    fetch("/api/v1/predictions/" + predictionId, { credentials: "same-origin" })
      .then(function (resp) {
        if (!resp.ok) throw new Error("Poll failed");
        return resp.json();
      })
      .then(function (data) {
        if (data.status === "completed") {
          window.location.href = "/results/" + predictionId;
        } else if (data.status === "failed") {
          showError(data.error_message || "Прогноз завершился с ошибкой");
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
