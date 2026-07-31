const GRADE_LABELS = {
  Teacher: "Teacher",
  M2: "M2",
  M1: "M1",
  B4: "B4",
  other: "other",
};

// 接続・切断・加算ループの revision 変化を検知する短い監視間隔
const WATCH_MS = 1000;
let watchTimer = null;
let lastRevision = null;
let rulesReady = false;

const els = {
  subtitle: document.getElementById("subtitle"),
  rules: document.getElementById("rules"),
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
  if (s >= 3600) return `${h}時間${m}分`;
  return `${m}分`;
}

function setSubtitle(status) {
  const updated = new Date().toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  els.subtitle.textContent = `最終更新: ${updated}`;
}

function formatRules(_status) {
  return (
    "Wi‑Fi 接続通知（POST /wifi_connected）で在室、切断通知（POST /wifi_disconnected）で不在とします。\n" +
    "総在室時間は接続中に加算し、切断時に確定します。"
  );
}

function presenceView(t) {
  if (!t.present) {
    return { rowClass: "row-away", statusClass: "status-away", label: "不在" };
  }
  return { rowClass: "row-present", statusClass: "status-present", label: "在室" };
}

function renderBoards(status) {
  setSubtitle(status);
  if (els.rules) {
    els.rules.textContent = formatRules(status);
    rulesReady = true;
  }

  const grades = status.grades || ["Teacher", "M2", "M1", "B4", "other"];
  const byGrade = status.by_grade || {};

  els.boards.innerHTML = grades
    .map((grade) => {
      const rows = byGrade[grade] || [];
      const body =
        rows.length === 0
          ? `<p class="empty">今日はまだ来ていません</p>`
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
                    const view = presenceView(t);
                    return `<tr class="${view.rowClass}">
                      <td class="${view.statusClass}">${view.label}</td>
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

async function watch() {
  try {
    const res = await fetch("/status", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const status = await res.json();
    const revision = status.revision;

    // 初回、または ARP完了・接続などで revision が変わったときだけ描画
    if (lastRevision === null || revision !== lastRevision) {
      lastRevision = revision;
      renderBoards(status);
    } else if (!rulesReady && els.rules) {
      els.rules.textContent = formatRules(status);
      rulesReady = true;
    }
  } catch (err) {
    els.subtitle.textContent = `最終更新: 失敗`;
    if (els.rules) els.rules.textContent = `更新失敗: ${err.message}`;
  }

  clearTimeout(watchTimer);
  watchTimer = setTimeout(watch, WATCH_MS);
}

formatClock();
setInterval(formatClock, 1000);
watch();
