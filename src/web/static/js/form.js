/**
 * src/web/static/js/form.js
 *
 * Handles the prediction form on the landing page:
 * - Debounced autocomplete for the outlet field (GET /api/v1/outlets?q=...)
 * - Form submission via fetch (POST /api/v1/predictions)
 * - Redirect to progress page on success
 */

(function () {
  "use strict";

  // --- DOM references ---
  var form = document.getElementById("prediction-form");
  var outletInput = document.getElementById("outlet");
  var suggestionsList = document.getElementById("outlet-suggestions");
  var dateInput = document.getElementById("target_date");
  var submitBtn = document.getElementById("submit-btn");
  var errorDiv = document.getElementById("form-error");

  if (!form || !outletInput) return;

  // --- Preset card selection ---
  var presetCards = document.querySelectorAll(".fn-preset-card");
  presetCards.forEach(function (card) {
    var radio = card.querySelector('input[type="radio"]');
    if (radio) {
      radio.addEventListener("change", function () {
        presetCards.forEach(function (c) {
          c.classList.remove("fn-preset-card--selected");
        });
        if (radio.checked) {
          card.classList.add("fn-preset-card--selected");
        }
      });
    }
  });

  // --- Autocomplete state ---
  var debounceTimer = null;
  var DEBOUNCE_MS = 300;
  var MIN_QUERY_LENGTH = 2;
  var selectedIndex = -1;

  // --- Autocomplete: fetch suggestions ---

  /**
   * Fetch outlet suggestions from the API.
   * @param {string} query - Search string (min 2 chars).
   */
  async function fetchSuggestions(query) {
    if (query.length < MIN_QUERY_LENGTH) {
      hideSuggestions();
      return;
    }

    try {
      var resp = await fetch(
        "/api/v1/outlets?" + new URLSearchParams({ q: query })
      );
      if (!resp.ok) return;

      var data = await resp.json();
      renderSuggestions(data.items || []);
    } catch (err) {
      // Network error -- silently ignore, user can type manually
    }
  }

  /**
   * Render suggestion items into the dropdown.
   * @param {Array<{name: string, language: string}>} outlets
   */
  function renderSuggestions(outlets) {
    // Clear previous suggestions safely
    while (suggestionsList.firstChild) {
      suggestionsList.removeChild(suggestionsList.firstChild);
    }
    selectedIndex = -1;

    if (outlets.length === 0) {
      // Show "not found" hint instead of hiding
      var hint = document.createElement("li");
      hint.setAttribute("role", "option");
      hint.className = "text-text-muted italic";
      hint.textContent = "Издание не найдено";
      suggestionsList.appendChild(hint);
      suggestionsList.hidden = false;
      return;
    }

    outlets.forEach(function (outlet, i) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      li.setAttribute("data-index", String(i));
      li.textContent = outlet.name;
      if (outlet.language) {
        var lang = document.createElement("small");
        lang.textContent = " (" + outlet.language + ")";
        li.appendChild(lang);
      }
      li.addEventListener("mousedown", function (e) {
        e.preventDefault(); // Prevent blur before click registers
        selectSuggestion(outlet.name);
      });
      suggestionsList.appendChild(li);
    });

    suggestionsList.hidden = false;
  }

  function hideSuggestions() {
    suggestionsList.hidden = true;
    while (suggestionsList.firstChild) {
      suggestionsList.removeChild(suggestionsList.firstChild);
    }
    selectedIndex = -1;
  }

  /**
   * Set the outlet input to the selected value and close dropdown.
   * @param {string} name
   */
  function selectSuggestion(name) {
    outletInput.value = name;
    hideSuggestions();
  }

  // --- Autocomplete: event listeners ---

  outletInput.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      fetchSuggestions(outletInput.value.trim());
    }, DEBOUNCE_MS);
  });

  outletInput.addEventListener("blur", function () {
    // Small delay to allow click on suggestion to register
    setTimeout(hideSuggestions, 150);
  });

  outletInput.addEventListener("focus", function () {
    if (outletInput.value.trim().length >= MIN_QUERY_LENGTH) {
      fetchSuggestions(outletInput.value.trim());
    }
  });

  // Keyboard navigation in dropdown
  outletInput.addEventListener("keydown", function (e) {
    var items = suggestionsList.querySelectorAll("li");
    if (!items.length || suggestionsList.hidden) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
      highlightItem(items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selectedIndex = Math.max(selectedIndex - 1, 0);
      highlightItem(items);
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      selectSuggestion(items[selectedIndex].textContent.split(" (")[0]);
    } else if (e.key === "Escape") {
      hideSuggestions();
    }
  });

  /**
   * Highlight the active item in the suggestions list.
   * @param {NodeList} items
   */
  function highlightItem(items) {
    items.forEach(function (item, i) {
      item.classList.toggle("fn-autocomplete-active", i === selectedIndex);
    });
  }

  // --- Date validation ---

  dateInput.addEventListener("change", function () {
    // Browser-native min/max validation handles most cases.
    // This adds a visual confirmation that the date is valid.
    var val = dateInput.value;
    if (!val) return;

    var selected = new Date(val);
    var today = new Date();
    today.setHours(0, 0, 0, 0);

    if (selected <= today) {
      dateInput.setCustomValidity("Выберите дату в будущем");
    } else {
      dateInput.setCustomValidity("");
    }
  });

  // --- Form submission ---

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    showError(""); // Clear previous errors

    var outlet = outletInput.value.trim();
    var targetDate = dateInput.value;

    if (!outlet) {
      showError("Укажите название СМИ");
      outletInput.focus();
      return;
    }

    if (!targetDate) {
      showError("Укажите дату прогноза");
      dateInput.focus();
      return;
    }

    // Disable form while submitting
    submitBtn.setAttribute("aria-busy", "true");
    submitBtn.disabled = true;

    try {
      var resp = await fetch("/api/v1/predictions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(
          (function () {
            var payload = {
              outlet: outlet,
              target_date: targetDate,
              preset: (function () {
                var r = form.querySelector('input[name="preset"]:checked');
                return r ? r.value : "standard";
              })(),
            };
            var apiKeyInput = document.getElementById("api_key");
            if (apiKeyInput && apiKeyInput.value.trim()) {
              payload.api_key = apiKeyInput.value.trim();
            }
            return payload;
          })()
        ),
      });

      if (!resp.ok) {
        var errData = await resp.json().catch(function () {
          return { detail: "Ошибка сервера" };
        });
        showError(errData.detail || "Не удалось создать прогноз");
        return;
      }

      var data = await resp.json();

      // Redirect to the progress page
      window.location.href = "/predict/" + data.id;
    } catch (err) {
      showError("Ошибка сети. Проверьте подключение к интернету.");
    } finally {
      submitBtn.removeAttribute("aria-busy");
      submitBtn.disabled = false;
    }
  });

  /**
   * Display or hide the error message.
   * @param {string} msg - Error text (empty to hide).
   */
  function showError(msg) {
    if (!msg) {
      errorDiv.hidden = true;
      errorDiv.textContent = "";
      return;
    }
    errorDiv.textContent = msg;
    errorDiv.hidden = false;
  }
})();
