const GRADE_LABELS = {
  Teacher: "Teacher",
  M2: "M2",
  M1: "M1",
  B4: "B4",
  other: "other",
};

const DEFAULT_POLL_SECONDS = 10;
let pollTimer = null;

const els = {
  subtitle: document.getElementById("subtitle"),
  clockDate: document.getElementById("clock-date"),
  clockTime: document.getElementById("clock-time"),
  boards: document.getElementById("boards"),
};

function dash(value) {
  return value == null || value === "" ? "-" : String(value);
}

function formatClock() {
  const now = new Date();
  els.clockDate.textContent = now.toLocaleDateString("ja-JP", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  });
  els.clockTime.textContent = now.toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  // 1時間を超えたら（＝1時間以上）〇時間〇分
  if (s >= 3600) return `${h}時間${m}分`;
  return `${m}分`;
}

function formatInterval(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  if (s < 60) return `${s}秒`;
  if (s < 3600) {
    const m = s / 60;
    return Number.isInteger(m) ? `${m}分` : `${parseFloat(m.toFixed(1))}分`;
  }
  const h = s / 3600;
  return Number.isInteger(h) ? `${h}時間` : `${parseFloat(h.toFixed(1))}時間`;
}

function formatLastUpdated(date, intervalSeconds) {
  const time = date.toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return `最終更新: ${time}（${formatInterval(intervalSeconds)}毎に自動更新）`;
}

function renderBoards(status) {
  const interval = status.check_interval_seconds || 0;
  els.subtitle.textContent = formatLastUpdated(new Date(), interval);

  const grades = status.grades || ["Teacher", "M2", "M1", "B4", "other"];
  const byGrade = status.by_grade || {};

  els.boards.innerHTML = grades
    .map((grade) => {
      const rows = byGrade[grade] || [];
      const body =
        rows.length === 0
          ? `<p class="empty">まだいません</p>`
          : `<table>
              <thead>
                <tr>
                  <th>状態</th>
                  <th>氏名</th>
                  <th>到着</th>
                  <th>帰宅</th>
                  <th>総在室</th>
                </tr>
              </thead>
              <tbody>
                ${rows
                  .map((t) => {
                    const present = !!t.present;
                    return `<tr>
                      <td class="${present ? "status-present" : "status-away"}">${
                        present ? "在室" : "不在"
                      }</td>
                      <td>${dash(t.name)}</td>
                      <td>${formatTime(t.arrived_at)}</td>
                      <td>${formatTime(t.left_at)}</td>
                      <td>${formatDuration(t.total_present_seconds)}</td>
                    </tr>`;
                  })
                  .join("")}
              </tbody>
            </table>`;

      return `<section class="board" data-grade="${grade}">
        <h2 class="board-title">${GRADE_LABELS[grade] || grade}</h2>
        ${body}
      </section>`;
    })
    .join("");
}

async function poll() {
  let nextSeconds = DEFAULT_POLL_SECONDS;
  try {
    const res = await fetch("/status", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const status = await res.json();
    nextSeconds = status.check_interval_seconds || DEFAULT_POLL_SECONDS;
    renderBoards(status);
  } catch (err) {
    els.subtitle.textContent = `更新失敗: ${err.message}`;
  }

  clearTimeout(pollTimer);
  pollTimer = setTimeout(poll, Math.max(1, nextSeconds) * 1000);
}

formatClock();
setInterval(formatClock, 1000);
poll();
