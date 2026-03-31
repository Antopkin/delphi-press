/**
 * Settings page — API key management.
 *
 * Handles add/delete/validate operations via fetch() to /api/v1/keys.
 * Cookie auth is sent automatically on same-origin requests.
 */
(function () {
  "use strict";

  var addForm = document.getElementById("add-key-form");
  var addBtn = document.getElementById("add-key-btn");
  var errorEl = document.getElementById("add-key-error");
  var successEl = document.getElementById("add-key-success");

  // ── Add key ───────────────────────────────────────────────────

  if (addForm) {
    addForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      errorEl.hidden = true;
      successEl.hidden = true;

      var provider = document.getElementById("provider").value;
      var apiKey = document.getElementById("api_key").value;
      var label = document.getElementById("label").value;

      if (apiKey.length < 10) {
        errorEl.textContent = "API-ключ должен быть не менее 10 символов.";
        errorEl.hidden = false;
        return;
      }

      addBtn.setAttribute("aria-busy", "true");
      addBtn.disabled = true;

      try {
        var resp = await fetch("/api/v1/keys", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            provider: provider,
            api_key: apiKey,
            label: label || undefined,
          }),
        });

        if (resp.ok) {
          successEl.textContent = "Ключ добавлен.";
          successEl.hidden = false;
          setTimeout(function () {
            window.location.reload();
          }, 800);
        } else {
          var data = await resp.json();
          errorEl.textContent = data.detail || "Ошибка при добавлении ключа.";
          errorEl.hidden = false;
        }
      } catch (err) {
        errorEl.textContent = "Ошибка сети: " + err.message;
        errorEl.hidden = false;
      } finally {
        addBtn.removeAttribute("aria-busy");
        addBtn.disabled = false;
      }
    });
  }

  // ── Delete key ────────────────────────────────────────────────

  document.querySelectorAll(".fn-delete-btn").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      if (!confirm("Удалить этот API-ключ?")) return;

      var keyId = btn.getAttribute("data-key-id");
      btn.setAttribute("aria-busy", "true");

      try {
        var resp = await fetch("/api/v1/keys/" + keyId, {
          method: "DELETE",
          credentials: "same-origin",
        });

        if (resp.ok || resp.status === 204) {
          window.location.reload();
        } else {
          alert("Ошибка при удалении ключа.");
        }
      } catch (err) {
        alert("Ошибка сети: " + err.message);
      } finally {
        btn.removeAttribute("aria-busy");
      }
    });
  });

  // ── Validate key ──────────────────────────────────────────────

  document.querySelectorAll(".fn-validate-btn").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      var keyId = btn.getAttribute("data-key-id");
      var resultEl = document.querySelector(
        '.fn-validate-result[data-key-id="' + keyId + '"]'
      );

      btn.setAttribute("aria-busy", "true");
      resultEl.textContent = "";

      try {
        var resp = await fetch("/api/v1/keys/" + keyId + "/validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
        });

        if (resp.ok) {
          var data = await resp.json();
          if (data.valid) {
            resultEl.textContent = "Ключ валиден.";
            resultEl.style.color = "var(--fn-step-done)";
          } else {
            resultEl.textContent = data.message || "Ключ невалиден.";
            resultEl.style.color = "var(--fn-confidence-speculative)";
          }
        } else {
          resultEl.textContent = "Ошибка проверки.";
          resultEl.style.color = "var(--fn-confidence-speculative)";
        }
      } catch (err) {
        resultEl.textContent = "Ошибка сети.";
        resultEl.style.color = "var(--fn-confidence-speculative)";
      } finally {
        btn.removeAttribute("aria-busy");
      }
    });
  });
})();
