/**
 * src/web/static/js/reveal.js
 *
 * Scroll-reveal utility using IntersectionObserver.
 * Elements with [data-reveal] attribute fade-in when entering viewport.
 * Works with CSS rules in custom.css section 17 (scroll-reveal & stagger).
 */

(function () {
  "use strict";

  if (!("IntersectionObserver" in window)) return;

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("fn-revealed");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1 }
  );

  document.querySelectorAll("[data-reveal]").forEach(function (el) {
    observer.observe(el);
  });
})();
