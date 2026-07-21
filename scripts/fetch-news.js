const { XMLParser } = require("fast-xml-parser");
const Anthropic = require("@anthropic-ai/sdk");

const PROJECT_ID = "news-utsushi";
const RAW_FETCH_COUNT = 20; // 信頼できる出典で絞り込む前提で多めに取得する
const MAX_ITEMS = 8; // 絞り込み後、表示する件数
const AI_COMMENT_MODEL = "claude-haiku-4-5";
const AI_COMMENT_MAX_TOKENS = 700;

// ANTHROPIC_API_KEYが無い環境(ローカル試験時など)ではAIコメント生成をスキップする。
const anthropicClient = process.env.ANTHROPIC_API_KEY ? new Anthropic() : null;

// カテゴリごとのGoogle Newsの検索キーワード。日本語ニュースに絞る。
const CATEGORIES = [
  {
    id: "ma",
    label: "M&A",
    query: "M&A OR 買収 OR TOB OR 経営統合 OR 資本業務提携",
  },
  {
    id: "keiei",
    label: "経営企画",
    query: "経営企画 OR 中期経営計画 OR 事業戦略 OR PMI OR 事業ポートフォリオ",
  },
  {
    id: "ai",
    label: "AI",
    query: "生成AI OR ChatGPT OR Claude OR OpenAI OR (AI 活用) OR (AI ビジネス)",
  },
  {
    id: "kyodo",
    label: "経堂・世田谷区",
    query: "経堂 OR (世田谷区 グルメ) OR (世田谷区 イベント) OR (世田谷区 ビジネス) OR (世田谷区 商店街)",
  },
  {
    id: "gunma",
    label: "群馬県",
    query: "群馬県 OR (群馬県 経済) OR (群馬県 企業) OR (群馬県 ビジネス) OR (群馬県 県政)",
  },
  {
    id: "kyoyo",
    label: "一般教養",
    query: "教養 OR ビジネス教養 OR (歴史 コラム) OR (科学 コラム) OR 時事解説",
  },
];

// Google Newsの表記ゆれを考慮した部分一致で判定する、信頼できる出典(発行元)の一覧。
// ここに含まれない出典の記事は「出所が確認しづらい」として除外する。
const TRUSTED_SOURCES = [
  "NHK",
  "日本経済新聞",
  "日経",
  "朝日新聞",
  "読売新聞",
  "毎日新聞",
  "産経新聞",
  "東京新聞",
  "中日新聞",
  "時事通信",
  "共同通信",
  "ロイター",
  "Reuters",
  "ブルームバーグ",
  "Bloomberg",
  "ITmedia",
  "Impress Watch",
  "ダイヤモンド",
  "東洋経済",
  "ビジネス+IT",
  "CNET Japan",
  "TechCrunch",
  "ハフポスト",
  "NHKニュース",
  "上毛新聞",
  "群馬テレビ",
  "東京新聞TOKYO Web",
  "経済新聞", // 「〇〇経済新聞」形式の地域経済ニュースネットワーク(二子玉川経済新聞、三軒茶屋経済新聞など)を含む
];

function isTrustedSource(source) {
  if (!source) return false;
  return TRUSTED_SOURCES.some((trusted) => source.includes(trusted));
}

function buildRssUrl(query) {
  const params = new URLSearchParams({
    q: query,
    hl: "ja",
    gl: "JP",
    ceid: "JP:ja",
  });
  return `https://news.google.com/rss/search?${params.toString()}`;
}

function stripHtml(html) {
  return String(html ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

const AI_COMMENT_SYSTEM_PROMPT = `あなたはビジネスセンスを鍛えたい読者向けに、ニュース記事の背景とビジネス的な意味を解説するアナリストです。
与えられた記事について、日本語で300〜400文字程度の解説コメントを書いてください。必ず次の観点を含めてください。

1. 誰が、何のために、この出来事を行った(または起きた)のか、という背景。
2. これがビジネスにどうつながるか。一見ビジネスと関係なさそうな話題でも、必ずどこかにビジネス的な関わり(市場・競争・マネタイズ・産業構造など)があります。それがどこにあるかを具体的に指摘してください。

本文のみを出力してください。見出し、箇条書き記号、前置き(「この記事は」等)は不要です。断定できない場合は推測であることが分かる書き方にしてください。`;

async function generateAiComment(category, item) {
  if (!anthropicClient) return "";
  try {
    const userContent = [
      `カテゴリ: ${category.label}`,
      `タイトル: ${item.title}`,
      `出典: ${item.source}(${item.pubDate})`,
      item.description ? `概要: ${item.description}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    const response = await anthropicClient.messages.create({
      model: AI_COMMENT_MODEL,
      max_tokens: AI_COMMENT_MAX_TOKENS,
      system: AI_COMMENT_SYSTEM_PROMPT,
      messages: [{ role: "user", content: userContent }],
    });

    const textBlock = response.content.find((b) => b.type === "text");
    return textBlock ? textBlock.text.trim() : "";
  } catch (e) {
    console.error(`[fetch-news] AIコメント生成失敗 (${category.id} / ${item.title}): ${e.message}`);
    return "";
  }
}

async function fetchCategoryItems(category) {
  const url = buildRssUrl(category.query);
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (compatible; news-app-fetcher/1.0)" },
  });
  if (!res.ok) {
    throw new Error(`RSS取得失敗 (${category.id}): HTTP ${res.status}`);
  }
  const xml = await res.text();
  const parser = new XMLParser({ ignoreAttributes: false });
  const parsed = parser.parse(xml);
  const rawItems = parsed?.rss?.channel?.item;
  const items = Array.isArray(rawItems) ? rawItems : rawItems ? [rawItems] : [];

  const normalized = items.slice(0, RAW_FETCH_COUNT).map((item) => {
    const rawTitle = String(item.title ?? "").trim();
    const source =
      typeof item.source === "object" ? String(item.source["#text"] ?? "").trim() : String(item.source ?? "").trim();
    // Google NewsのタイトルはRSSタグ末尾に発行元名が重複して付くことがあるため取り除く。
    const title = source && rawTitle.endsWith(` - ${source}`) ? rawTitle.slice(0, -(` - ${source}`.length)) : rawTitle;
    const description = stripHtml(item.description);
    return {
      title,
      link: String(item.link ?? "").trim(),
      source,
      pubDate: String(item.pubDate ?? "").trim(),
      // タイトルと同じ・空・過度に長いだけの説明文は表示価値が低いため省く。
      description: description && description !== title && description.length < 300 ? description : "",
    };
  });

  return normalized.filter((item) => isTrustedSource(item.source)).slice(0, MAX_ITEMS);
}

function toFirestoreValue(value) {
  if (value === null || value === undefined) return { nullValue: null };
  if (typeof value === "string") return { stringValue: value };
  if (typeof value === "number") return { integerValue: String(value) };
  if (Array.isArray(value)) {
    return { arrayValue: { values: value.map(toFirestoreValue) } };
  }
  if (value instanceof Date) return { timestampValue: value.toISOString() };
  if (typeof value === "object") {
    const fields = {};
    for (const [k, v] of Object.entries(value)) fields[k] = toFirestoreValue(v);
    return { mapValue: { fields } };
  }
  return { stringValue: String(value) };
}

async function writeCategoryToFirestore(category, items) {
  const docPath = `newsItems/${category.id}`;
  const body = {
    fields: {
      label: toFirestoreValue(category.label),
      items: toFirestoreValue(items),
      fetchedAt: toFirestoreValue(new Date()),
    },
  };

  // PATCH(updateMask指定)はドキュメントが無ければ自動作成、あれば指定フィールドのみ更新する。
  const patchUrl =
    `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents/${docPath}` +
    `?updateMask.fieldPaths=items&updateMask.fieldPaths=label&updateMask.fieldPaths=fetchedAt`;

  const res = await fetch(patchUrl, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Firestore書き込み失敗 (${category.id}): HTTP ${res.status} ${text}`);
  }
}

async function main() {
  for (const category of CATEGORIES) {
    try {
      const items = await fetchCategoryItems(category);
      // AIコメントは1件ずつ順番に生成する(並列にすると同時レート制限に当たりやすいため)。
      for (const item of items) {
        item.aiComment = await generateAiComment(category, item);
      }
      await writeCategoryToFirestore(category, items);
      console.log(`[fetch-news] ${category.id}: ${items.length}件を保存しました`);
    } catch (e) {
      console.error(`[fetch-news] ${category.id} でエラー: ${e.message}`);
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
