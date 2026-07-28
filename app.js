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

  // iOSのSafariはawaitの後のwindow.open()をポップアップとしてブロックすることがあるため、
  // ユーザー操作の直後(同期的)に先にタブを開いてから、クリップボードへの書き込みを行う。
  // (noopenerを渡すと参照がnullになりlocationを後から設定できないため、開いた直後にopenerを切る)
  const newTab = window.open("", "_blank");
  if (newTab) newTab.opener = null;

  try {
    await navigator.clipboard.writeText(question);
  } catch (e) {
    console.error("クリップボードへのコピーに失敗しました", e);
  }

  if (newTab) {
    newTab.location = AI_CHAT_URL;
  } else {
    window.open(AI_CHAT_URL, "_blank", "noopener,noreferrer");
  }
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

  // ===== タップすると開閉するヘッダー(見出し) =====
  const header = document.createElement("button");
  header.type = "button";
  header.className = "news-header";

  const titleWrap = document.createElement("span");
  titleWrap.className = "news-title";
  titleWrap.textContent = item.title;
  header.appendChild(titleWrap);

  const meta = document.createElement("span");
  meta.className = "news-meta";
  const sourceBadge = document.createElement("span");
  sourceBadge.className = "source-badge";
  sourceBadge.textContent = item.source || "出典不明";
  meta.appendChild(sourceBadge);
  if (item.pubDate) {
    const dateSpan = document.createElement("span");
    dateSpan.className = "news-date";
    dateSpan.textContent = item.pubDate;
    meta.appendChild(dateSpan);
  }
  header.appendChild(meta);

  const chevron = document.createElement("span");
  chevron.className = "news-chevron";
  chevron.textContent = "▼";
  header.appendChild(chevron);

  header.addEventListener("click", () => {
    li.classList.toggle("expanded");
  });

  li.appendChild(header);

  // ===== 開いた時だけ見える詳細部分 =====
  const body = document.createElement("div");
  body.className = "news-body";

  if (item.description) {
    const desc = document.createElement("div");
    desc.className = "news-desc";
    desc.textContent = item.description;
    body.appendChild(desc);
  }

  if (item.aiComment) {
    const aiBox = document.createElement("div");
    aiBox.className = "ai-comment-box";
    const aiLabel = document.createElement("div");
    aiLabel.className = "ai-comment-label";
    aiLabel.textContent = "🤖 AI分析(背景・ビジネスとの関わり)";
    const aiText = document.createElement("div");
    aiText.className = "ai-comment-text";
    aiText.textContent = item.aiComment;
    aiBox.appendChild(aiLabel);
    aiBox.appendChild(aiText);
    body.appendChild(aiBox);
  }

  const footer = document.createElement("div");
  footer.className = "news-footer";

  const readMoreLink = document.createElement("a");
  readMoreLink.className = "btn-read-more";
  readMoreLink.href = item.link;
  readMoreLink.target = "_blank";
  readMoreLink.rel = "noopener noreferrer";
  readMoreLink.textContent = "🔗 元記事を読む";
  footer.appendChild(readMoreLink);

  const askBtn = document.createElement("button");
  askBtn.type = "button";
  askBtn.className = "btn-ask-ai";
  askBtn.textContent = "💬 もっとAIに聞く";
  askBtn.addEventListener("click", () => handleAskAi(item));
  footer.appendChild(askBtn);

  body.appendChild(footer);
  li.appendChild(body);

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

// ================= カテゴリ一覧⇔詳細画面の切り替え =================
// (PC幅では#category-menu/#detail-headerをCSSで非表示にし、全カテゴリを並べて表示する)
const appEl = document.getElementById("app");

function showCategory(categoryId) {
  appEl.classList.remove("mode-menu");
  appEl.classList.add("mode-detail");
  document.getElementById("detail-header").classList.remove("hidden");

  document.querySelectorAll("#news-sections .card").forEach((card) => {
    card.classList.toggle("active", card.dataset.category === categoryId);
  });
}

function showMenu() {
  appEl.classList.remove("mode-detail");
  appEl.classList.add("mode-menu");
  document.getElementById("detail-header").classList.add("hidden");
}

document.querySelectorAll(".category-btn").forEach((btn) => {
  btn.addEventListener("click", () => showCategory(btn.dataset.category));
});

document.getElementById("btn-back").addEventListener("click", showMenu);

renderTodayDate();
showMenu();
CATEGORY_IDS.forEach((id) => loadNewsCategory(id));
