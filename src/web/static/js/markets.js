/**
 * markets.js — Chart.js sparklines for /markets dashboard.
 *
 * Each <canvas class="fn-sparkline" data-prices="[0.5, 0.52, ...]">
 * gets a compact line chart (no axes, no legend, no grid).
 */

document.addEventListener("DOMContentLoaded", () => {
  const canvases = document.querySelectorAll(".fn-sparkline");
  if (!canvases.length || typeof Chart === "undefined") return;

  // Primary color from CSS custom property (OKLCH → fallback hex)
  const primaryColor =
    getComputedStyle(document.documentElement)
      .getPropertyValue("--color-primary")
      .trim() || "#3b5bdb";

  canvases.forEach((canvas) => {
    let prices;
    try {
      prices = JSON.parse(canvas.dataset.prices || "[]");
    } catch {
      return;
    }
    if (prices.length < 2) return;

    // Determine trend color: green if up, red if down, primary if flat
    const first = prices[0];
    const last = prices[prices.length - 1];
    let lineColor = primaryColor;
    if (last > first + 0.01) lineColor = "oklch(58% 0.17 145)"; // green
    if (last < first - 0.01) lineColor = "oklch(52% 0.20 25)";  // red

    new Chart(canvas, {
      type: "line",
      data: {
        labels: prices.map((_, i) => i),
        datasets: [
          {
            data: prices,
            borderColor: lineColor,
            borderWidth: 1.5,
            pointRadius: 0,
            pointHitRadius: 0,
            tension: 0.3,
            fill: false,
          },
        ],
      },
      options: {
        responsive: false,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: { enabled: false },
        },
        scales: {
          x: { display: false },
          y: { display: false },
        },
        layout: { padding: 2 },
      },
    });
  });
});
