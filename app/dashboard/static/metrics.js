async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function formatStatusPill(status) {
  const pill = document.createElement("span");
  pill.className = `pill ${status}`;
  pill.textContent = status.replaceAll("_", " ");
  return pill;
}

function renderSummary(metrics, bills) {
  document.getElementById("total-bills").textContent = metrics.total_bills ?? 0;
  document.getElementById("avg-confidence").textContent =
    metrics.avg_confidence_score == null ? "--" : `${Math.round(metrics.avg_confidence_score * 100)}%`;

  const byStatus = metrics.by_status || {};
  document.getElementById("awaiting-review").textContent = byStatus.awaiting_review ?? 0;
  document.getElementById("processing").textContent =
    (byStatus.pending ?? 0) + (byStatus.processing ?? 0);

  const recentTable = document.getElementById("recent-bills");
  recentTable.innerHTML = "";

  if (!bills.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="5" class="empty-state">No freight bills found yet.</td>`;
    recentTable.appendChild(row);
    return;
  }

  for (const bill of bills.slice(0, 10)) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>
        <div class="row-title">${bill.id}</div>
        <div class="row-sub">${bill.bill_number}</div>
      </td>
      <td>${bill.carrier_name}</td>
      <td>${bill.lane ?? "--"}</td>
      <td>${bill.confidence_score == null ? "--" : `${Math.round(bill.confidence_score * 100)}%`}</td>
      <td></td>
    `;
    row.children[4].appendChild(formatStatusPill(bill.status || "unknown"));
    recentTable.appendChild(row);
  }
}

function renderStatusBreakdown(metrics) {
  const byStatus = metrics.by_status || {};
  const container = document.getElementById("status-breakdown");
  container.innerHTML = "";

  const entries = Object.entries(byStatus);
  if (!entries.length) {
    container.innerHTML = `<p class="empty-state">No stage data available yet.</p>`;
    return;
  }

  for (const [status, count] of entries) {
    const item = document.createElement("div");
    item.className = "queue-item";
    item.innerHTML = `
      <div class="queue-head">
        <div>
          <h3 class="queue-title">${status.replaceAll("_", " ")}</h3>
          <p class="queue-sub">Current workflow stage count.</p>
        </div>
        <div class="stat">${count}</div>
      </div>
    `;
    container.appendChild(item);
  }
}

function renderDecisionBreakdown(metrics) {
  const byDecision = metrics.by_decision || {};
  const container = document.getElementById("decision-breakdown");
  container.innerHTML = "";

  const entries = Object.entries(byDecision);
  if (!entries.length) {
    container.innerHTML = `<p class="empty-state">No final decisions recorded yet.</p>`;
    return;
  }

  for (const [decision, count] of entries) {
    const item = document.createElement("div");
    item.className = "queue-item";
    item.innerHTML = `
      <div class="queue-head">
        <div>
          <h3 class="queue-title">${decision.replaceAll("_", " ")}</h3>
          <p class="queue-sub">Bills that reached this outcome.</p>
        </div>
        <div class="stat">${count}</div>
      </div>
    `;
    container.appendChild(item);
  }
}

async function loadMetricsPage() {
  const status = document.getElementById("page-status");
  try {
    const [metrics, bills] = await Promise.all([
      fetchJson("/metrics"),
      fetchJson("/freight-bills"),
    ]);
    renderSummary(metrics, bills);
    renderStatusBreakdown(metrics);
    renderDecisionBreakdown(metrics);
    status.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    status.textContent = "Could not load metrics right now.";
    console.error(error);
  }
}

document.getElementById("refresh-metrics").addEventListener("click", loadMetricsPage);
loadMetricsPage();
