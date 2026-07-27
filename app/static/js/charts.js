/* Dashboard charts.
   Data comes from /api/charts so the numbers are inspectable by hand. */

(function () {
  "use strict";

  const INK = "#141A22";
  const INK_SOFT = "#8A93A1";
  const RULE = "#E9ECF1";
  const ACCENT = "#24406B";
  const OVER = "#A5372E";
  const MONO = "'IBM Plex Mono', ui-monospace, monospace";
  const SANS = "'IBM Plex Sans', system-ui, sans-serif";

  if (typeof Chart === "undefined") return;

  Chart.defaults.font.family = SANS;
  Chart.defaults.font.size = 12;
  Chart.defaults.color = INK_SOFT;
  Chart.defaults.animation.duration =
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 400;

  const currency = (value) =>
    "$" + Number(value).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });

  const currencyExact = (value) =>
    "$" + Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const moneyAxis = {
    grid: { color: RULE, drawTicks: false },
    border: { display: false },
    ticks: { callback: currency, font: { family: MONO, size: 11 }, padding: 8 },
  };

  function categoryMix(canvas, data) {
    const rows = data.byCategory.filter((row) => row.spent > 0);
    if (!rows.length) return emptyState(canvas, "No spending recorded this month");

    new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: rows.map((row) => row.name),
        datasets: [
          {
            data: rows.map((row) => row.spent),
            backgroundColor: rows.map((row) => row.color),
            borderColor: "#FFFFFF",
            borderWidth: 2,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        cutout: "62%",
        plugins: {
          legend: {
            position: "right",
            labels: { boxWidth: 9, boxHeight: 9, usePointStyle: true, pointStyle: "rectRounded", padding: 11 },
          },
          tooltip: {
            callbacks: {
              label: (item) => {
                const total = item.dataset.data.reduce((sum, value) => sum + value, 0);
                const share = total ? Math.round((item.raw / total) * 100) : 0;
                return ` ${currencyExact(item.raw)} · ${share}%`;
              },
            },
          },
        },
      },
    });
  }

  function burnDown(canvas, data) {
    const burn = data.burnDown;
    const labels = burn.series.map((point) => point.day);
    const actual = burn.series.map((point) => point.total);

    const datasets = [
      {
        label: "Spent so far",
        data: actual,
        borderColor: ACCENT,
        backgroundColor: "rgba(36, 64, 107, .10)",
        fill: true,
        tension: 0.25,
        pointRadius: 0,
        pointHoverRadius: 4,
        borderWidth: 2,
        spanGaps: false,
      },
    ];

    // The straight line an even burn rate would trace across the month.
    if (burn.limit) {
      datasets.push({
        label: "Even pace",
        data: labels.map((day) => (burn.limit / burn.daysInMonth) * day),
        borderColor: OVER,
        borderDash: [5, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
        tension: 0,
      });
    }

    new Chart(canvas, {
      type: "line",
      data: { labels, datasets },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          y: { ...moneyAxis, beginAtZero: true },
          x: {
            grid: { display: false },
            border: { color: RULE },
            ticks: { font: { family: MONO, size: 11 }, maxTicksLimit: 8 },
          },
        },
        plugins: {
          legend: { display: true, labels: { boxWidth: 14, boxHeight: 2, padding: 12 } },
          tooltip: {
            callbacks: {
              title: (items) => "Day " + items[0].label,
              label: (item) => ` ${item.dataset.label}: ${currencyExact(item.raw)}`,
            },
          },
        },
      },
    });
  }

  function history(canvas, data) {
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: data.history.map((row) => row.label),
        datasets: [
          {
            label: "Total spent",
            data: data.history.map((row) => row.total),
            backgroundColor: data.history.map((row, index) =>
              index === data.history.length - 1 ? ACCENT : "rgba(36, 64, 107, .32)"
            ),
            borderRadius: 4,
            maxBarThickness: 44,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        scales: {
          y: { ...moneyAxis, beginAtZero: true },
          x: { grid: { display: false }, border: { color: RULE }, ticks: { font: { family: MONO, size: 11 } } },
        },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (item) => " " + currencyExact(item.raw) } },
        },
      },
    });
  }

  function emptyState(canvas, message) {
    const box = canvas.parentElement;
    box.innerHTML = '<p class="muted" style="text-align:center;padding-top:80px">' + message + "</p>";
  }

  async function start() {
    const month = window.LEDGER_MONTH || "";
    let data;
    try {
      const response = await fetch("/api/charts?month=" + encodeURIComponent(month));
      if (!response.ok) throw new Error(response.statusText);
      data = await response.json();
    } catch (error) {
      document.querySelectorAll(".chartbox canvas").forEach((canvas) =>
        emptyState(canvas, "Charts couldn't load. Refresh to try again.")
      );
      return;
    }

    const mix = document.getElementById("chart-mix");
    const burn = document.getElementById("chart-burn");
    const trend = document.getElementById("chart-history");

    if (mix) categoryMix(mix, data);
    if (burn) burnDown(burn, data);
    if (trend) history(trend, data);
  }

  document.addEventListener("DOMContentLoaded", start);
})();
