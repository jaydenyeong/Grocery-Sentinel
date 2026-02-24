const API_BASE = window.API_BASE || "http://127.0.0.1:8000";
const REFRESH_INTERVAL_MS = 60_000;

let items = [];
let sortKey = "last_updated";
let sortAsc = false;
let chart;

const itemsBody = document.getElementById("itemsBody");
const searchInput = document.getElementById("searchInput");
const refreshBtn = document.getElementById("refreshBtn");
const historyPanel = document.getElementById("historyPanel");
const historyTitle = document.getElementById("historyTitle");
const chartCanvas = document.getElementById("historyChart");

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function money(value) {
  if (value === null || value === undefined) return "-";
  return `RM ${Number(value).toFixed(2)}`;
}

function percent(value) {
  if (value === null || value === undefined) return "-";
  return `${Number(value).toFixed(1)}%`;
}

function changeClass(direction) {
  return `change-${direction}`;
}

function changeText(item) {
  if (item.direction === "up") return `▲ +${Math.abs(item.price_change).toFixed(2)}`;
  if (item.direction === "down") return `▼ -${Math.abs(item.price_change).toFixed(2)}`;
  if (item.direction === "new") return "• New";
  return "→ 0.00";
}

function relativeTime(isoValue) {
  const diffMs = Date.now() - new Date(isoValue).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return `${days} day ago`;
}

function compare(a, b) {
  const av = a[sortKey];
  const bv = b[sortKey];

  let result = 0;
  if (sortKey === "last_updated") {
    result = new Date(av).getTime() - new Date(bv).getTime();
  } else if (typeof av === "number" && typeof bv === "number") {
    result = av - bv;
  } else {
    result = String(av ?? "").localeCompare(String(bv ?? ""));
  }

  return sortAsc ? result : -result;
}

function filteredItems() {
  const keyword = searchInput.value.trim().toLowerCase();
  return items.filter(
    (item) => item.product_name.toLowerCase().includes(keyword) || item.store.toLowerCase().includes(keyword),
  ).sort(compare);
}

function renderTable() {
  const rows = filteredItems()
    .map((item) => {
      return `
        <tr data-id="${item.id}">
          <td>${item.product_name}</td>
          <td>${item.store}</td>
          <td>${money(item.current_price)}</td>
          <td>${money(item.previous_price)}</td>
          <td class="${changeClass(item.direction)}">${changeText(item)}</td>
          <td class="${changeClass(item.direction)}">${percent(item.percent_change)}</td>
          <td>${relativeTime(item.last_updated)}</td>
        </tr>
      `;
    })
    .join("");

  itemsBody.innerHTML = rows || "<tr><td colspan='7'>No items found.</td></tr>";
}

async function fetchJson(path) {
  const response = await fetch(apiUrl(path));
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Request failed (${response.status}): ${body}`);
  }
  return response.json();
}

async function loadItems() {
  try {
    items = await fetchJson("/items");
    renderTable();
  } catch (error) {
    console.error("Failed to load items", error);
  }
}

async function loadHistory(itemId) {
  try {
    const data = await fetchJson(`/history/${itemId}`);

    historyPanel.classList.remove("hidden");
    historyTitle.textContent = `Price History - ${data.product_name}`;

    const labels = data.history.map((point) => new Date(point.scraped_at).toLocaleString());
    const prices = data.history.map((point) => point.price);

    if (chart) chart.destroy();
    chart = new Chart(chartCanvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Price (RM)",
            data: prices,
            borderWidth: 2,
            tension: 0.2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
      },
    });
  } catch (error) {
    console.error(`Failed to load history for item ${itemId}`, error);
  }
}

document.querySelectorAll("th[data-key]").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    if (sortKey === key) {
      sortAsc = !sortAsc;
    } else {
      sortKey = key;
      sortAsc = true;
    }
    renderTable();
  });
});

searchInput.addEventListener("input", renderTable);
refreshBtn.addEventListener("click", loadItems);

itemsBody.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-id]");
  if (!row) return;
  loadHistory(row.dataset.id);
});

loadItems();
setInterval(loadItems, REFRESH_INTERVAL_MS);
