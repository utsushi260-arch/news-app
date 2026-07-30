/* ===== Kindle文字起こし(OCR)ロジック =====
 * 端末内(ブラウザ)でTesseract.jsを使って画像から文字を読み取る。
 * 画像は外部サーバーに送信されない。 */

(function () {
  "use strict";

  const els = {
    orientation: document.getElementById("orientation-group"),
    fileInput: document.getElementById("file-input"),
    thumbs: document.getElementById("thumbs"),
    btnRun: document.getElementById("btn-run"),
    progressCard: document.getElementById("progress-card"),
    progressFill: document.getElementById("progress-fill"),
    progressText: document.getElementById("progress-text"),
    resultCard: document.getElementById("result-card"),
    resultText: document.getElementById("result-text"),
    btnCopy: document.getElementById("btn-copy"),
    btnDownload: document.getElementById("btn-download"),
    btnClear: document.getElementById("btn-clear"),
    toast: document.getElementById("toast"),
  };

  let files = []; // 選択された画像(File)の配列
  let lang = "jpn_vert"; // 既定は縦書き
  let running = false;

  /* ---- 向き切り替え ---- */
  els.orientation.addEventListener("click", function (e) {
    const btn = e.target.closest(".seg-btn");
    if (!btn || running) return;
    lang = btn.dataset.lang;
    els.orientation.querySelectorAll(".seg-btn").forEach(function (b) {
      b.classList.toggle("active", b === btn);
    });
  });

  /* ---- ファイル選択 ---- */
  els.fileInput.addEventListener("change", function () {
    const picked = Array.from(els.fileInput.files || []).filter(function (f) {
      return f.type.startsWith("image/");
    });
    files = files.concat(picked);
    els.fileInput.value = ""; // 同じファイルを選び直せるようにリセット
    renderThumbs();
  });

  function renderThumbs() {
    els.thumbs.innerHTML = "";
    files.forEach(function (file, i) {
      const wrap = document.createElement("div");
      wrap.className = "thumb";

      const img = document.createElement("img");
      const url = URL.createObjectURL(file);
      img.src = url;
      img.onload = function () {
        URL.revokeObjectURL(url);
      };

      const idx = document.createElement("span");
      idx.className = "thumb-index";
      idx.textContent = i + 1;

      const rm = document.createElement("button");
      rm.className = "thumb-remove";
      rm.type = "button";
      rm.textContent = "×";
      rm.setAttribute("aria-label", (i + 1) + "枚目を削除");
      rm.addEventListener("click", function () {
        if (running) return;
        files.splice(i, 1);
        renderThumbs();
      });

      wrap.appendChild(img);
      wrap.appendChild(idx);
      wrap.appendChild(rm);
      els.thumbs.appendChild(wrap);
    });
    els.btnRun.disabled = files.length === 0 || running;
  }

  /* ---- 進捗表示 ---- */
  const STATUS_LABEL = {
    "loading tesseract core": "エンジンを読み込み中…",
    "initializing tesseract": "エンジンを準備中…",
    "loading language traineddata": "日本語データを読み込み中…",
    "initializing api": "準備中…",
    "recognizing text": "文字を認識中…",
  };

  function setProgress(ratio, label) {
    const pct = Math.max(0, Math.min(100, Math.round(ratio * 100)));
    els.progressFill.style.width = pct + "%";
    els.progressText.textContent = label + "（" + pct + "%）";
  }

  /* ---- OCR実行 ---- */
  els.btnRun.addEventListener("click", async function () {
    if (running || files.length === 0) return;
    if (typeof Tesseract === "undefined") {
      showToast("OCRエンジンを読み込めませんでした。通信環境をご確認のうえ再読み込みしてください。");
      return;
    }

    running = true;
    els.btnRun.disabled = true;
    els.btnRun.textContent = "処理中…";
    els.progressCard.classList.remove("hidden");
    els.resultCard.classList.add("hidden");
    setProgress(0, "準備中…");

    const total = files.length;
    let worker;

    try {
      worker = await Tesseract.createWorker(lang, 1, {
        logger: function (m) {
          const label = STATUS_LABEL[m.status] || m.status || "処理中…";
          // 全体進捗 = (完了画像数 + 現在画像の進捗) / 総数
          const base = Number(worker && worker.__done) || 0;
          const cur = typeof m.progress === "number" ? m.progress : 0;
          const overall = total > 0 ? (base + cur) / total : cur;
          setProgress(overall, total > 1 ? label + "  " + (base + 1) + "/" + total + "枚目" : label);
        },
      });

      const parts = [];
      for (let i = 0; i < files.length; i++) {
        worker.__done = i;
        const res = await worker.recognize(files[i]);
        parts.push(cleanText(res.data.text));
      }

      await worker.terminate();

      const joined = parts.join("\n\n").trim();
      els.resultText.value = joined || "（文字を読み取れませんでした。画像を大きく・鮮明にして再度お試しください）";
      els.resultCard.classList.remove("hidden");
      setProgress(1, "完了");
      els.resultCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      console.error(err);
      showToast("読み取り中にエラーが発生しました。もう一度お試しください。");
      if (worker) {
        try { await worker.terminate(); } catch (e) { /* noop */ }
      }
    } finally {
      running = false;
      els.btnRun.textContent = "文字起こしを開始";
      els.btnRun.disabled = files.length === 0;
      els.progressCard.classList.add("hidden");
    }
  });

  /* ---- テキスト整形: 日本語文字間の余計な空白を除去 ---- */
  function cleanText(text) {
    if (!text) return "";
    let t = text;
    // 非ASCII文字(=主に日本語)どうしの間の半角/全角スペースを除去
    t = t.replace(/([^\x00-\x7F])[ \t　]+(?=[^\x00-\x7F])/g, "$1");
    // 行末の空白除去
    t = t.replace(/[ \t　]+$/gm, "");
    // 3行以上の連続空行を2行に圧縮
    t = t.replace(/\n{3,}/g, "\n\n");
    return t.trim();
  }

  /* ---- コピー ---- */
  els.btnCopy.addEventListener("click", async function () {
    const text = els.resultText.value;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      showToast("コピーしました。");
    } catch (e) {
      // フォールバック
      els.resultText.select();
      document.execCommand("copy");
      showToast("コピーしました。");
    }
  });

  /* ---- ダウンロード(.txt) ---- */
  els.btnDownload.addEventListener("click", function () {
    const text = els.resultText.value;
    if (!text) return;
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "kindle-transcription.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  /* ---- クリア ---- */
  els.btnClear.addEventListener("click", function () {
    if (running) return;
    files = [];
    renderThumbs();
    els.resultText.value = "";
    els.resultCard.classList.add("hidden");
  });

  /* ---- トースト ---- */
  let toastTimer;
  function showToast(msg) {
    els.toast.textContent = msg;
    els.toast.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      els.toast.classList.add("hidden");
    }, 2600);
  }
})();
