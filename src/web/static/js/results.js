/**
 * src/web/static/js/results.js
 *
 * Handles interactive elements on the results page:
 * - <details> accordion: close others in the same section when one opens
 * - Scroll-reveal animations for timeline entries
 */

(function () {
  "use strict";

  // --- Accordion: close other <details> when one opens ---
  // Applies to reasoning blocks within headline cards.
  // Methodology section details are independent (can all be open).

  var headlineDetails = document.querySelectorAll(
    "[data-stagger] .fn-reasoning-block"
  );

  headlineDetails.forEach(function (details) {
    details.addEventListener("toggle", function () {
      if (!details.open) return;

      headlineDetails.forEach(function (other) {
        if (other !== details && other.open) {
          other.open = false;
        }
      });
    });
  });
})();
