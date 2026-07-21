import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getFirestore, doc, getDoc } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";
import { firebaseConfig } from "./firebase-config.js";

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

const AI_CHAT_URL = "https://claude.ai/new";
const CATEGORY_IDS = ["ma", "keiei", "ai", "kyodo", "gunma", "kyoyo"];

// ================= 今日の日付表示 =================
function renderTodayDate() {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "numeric",
    day: "numeric",
    weekday: "short",
  }).format(now);
  document.getElementById("today-date").textContent = parts;
}

// ================= AIに聞くボタン =================
function buildAiQuestion(item) {
  const lines = [
    "このニュースについて、背景や関連する情報を教えてください。",
    "",
    `タイトル: ${item.title}`,
    `出典: ${[item.source, item.pubDate].filter(Boolean).join(" ・ ")}`,
    `URL: ${item.link}`,
  ];
  if (item.description) {
    lines.push(`概要: ${item.description}`);
  }
  return lines.join("\n");
}

let toastTimer = null;
function showAiCopiedToast() {
  const el = document.getElementById("ai-copied-msg");
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 6000);
}

async function handleAskAi(item) {
  const question = buildAiQuestion(item);
  try {
    await navigator.clipboard.writeText(question);
  } catch (e) {
    console.error("クリップボードへのコピーに失敗しました", e);
  }
  window.open(AI_CHAT_URL, "_blank", "noopener,noreferrer");
  showAiCopiedToast();
}

// ================= ニュース表示 =================
function formatFetchedAt(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  const parts = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
  return `${parts} 時点`;
}

function renderNewsItem(item) {
  const li = document.createElement("li");
  li.className = "news-item";

  const a = document.createElement("a");
  a.href = item.link;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.textContent = item.title;
  li.appendChild(a);

  const meta = document.createElement("div");
  meta.className = "news-meta";
  meta.textContent = [item.source, item.pubDate].filter(Boolean).join(" ・ ");
  li.appendChild(meta);

  if (item.description) {
    const desc = document.createElement("div");
    desc.className = "news-desc";
    desc.textContent = item.description;
    li.appendChild(desc);
  }

  const askBtn = document.createElement("button");
  askBtn.type = "button";
  askBtn.className = "btn-ask-ai";
  askBtn.textContent = "🤖 AIに聞く";
  askBtn.addEventListener("click", () => handleAskAi(item));
  li.appendChild(askBtn);

  return li;
}

async function loadNewsCategory(categoryId) {
  const listEl = document.getElementById(`news-${categoryId}`);
  const fetchedAtEl = document.getElementById(`fetched-at-${categoryId}`);
  listEl.innerHTML = "";

  let snap;
  try {
    snap = await getDoc(doc(db, "newsItems", categoryId));
  } catch (e) {
    fetchedAtEl.textContent = "";
    listEl.innerHTML = '<li class="error-text">読み込みに失敗しました</li>';
    return;
  }

  if (!snap.exists()) {
    fetchedAtEl.textContent = "まだ取得されていません(初回のcron実行をお待ちください)";
    return;
  }

  const data = snap.data();
  fetchedAtEl.textContent = formatFetchedAt(data.fetchedAt?.toDate?.().toISOString?.() ?? data.fetchedAt);

  const items = data.items ?? [];
  if (items.length === 0) {
    listEl.innerHTML = '<li class="empty-text">該当する記事が見つかりませんでした</li>';
    return;
  }

  items.forEach((item) => listEl.appendChild(renderNewsItem(item)));
}

renderTodayDate();
CATEGORY_IDS.forEach((id) => loadNewsCategory(id));
