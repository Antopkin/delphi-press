/**
 * src/web/static/js/results.js
 *
 * Handles interactive elements on the results page:
 * - <details> accordion: optionally close others when one opens (UX polish)
 * - No other interactivity needed -- Pico.css + semantic HTML does the rest
 */

(function () {
  "use strict";

  // --- Optional: close other <details> when one opens ---
  // This creates an accordion effect for reasoning blocks.
  // Remove this if you want multiple blocks open simultaneously.

  var detailsElements = document.querySelectorAll(".fn-reasoning-block");

  detailsElements.forEach(function (details) {
    details.addEventListener("toggle", function () {
      if (!details.open) return;

      // Close all other open details in the same page
      detailsElements.forEach(function (other) {
        if (other !== details && other.open) {
          other.open = false;
        }
      });
    });
  });
})();
