/* 새 원고 만들기 — **끌어다 놓고, 길이 고르고, 단추.**
 *
 * 2026-08-14: "새 원고를 누르니 너무 복잡하게 나오는데... 드래그드랍만 나오게
 * 해주시면 안될까요?!" 맞는 말이었다. 이 화면은 폴더 경로 · 앞뒤로 버릴 쪽 ·
 * 미리보기 · 이름 넷을 한꺼번에 물었는데, **매번 답이 같은 질문들**이었다.
 * 매번 같은 답이 나오는 질문은 화면에 있을 이유가 없다 — 기본값으로 두고
 * 「자세히」 안으로 접는다. 남는 것은 셋이다:
 *
 *     PDF 를 끌어다 놓는다  →  몇 분짜리로 만들지 고른다  →  단추를 누른다
 *
 * ★ 브라우저는 **끌어다 놓은 파일의 진짜 경로를 안 알려 준다**(Electron 이 아니다).
 *   그래서 바이트를 서버로 올려 workspace 의 `_받은PDF/` 에 앉힌다. 예전에 업로드를
 *   피했던 이유는 13개 × 9MB 를 **base64 로 한 JSON 에** 실으면 브라우저가 버틴다는
 *   보장이 없어서였는데, 파일 하나당 한 요청으로 raw 로 보내면 그 문제가 없다.
 *   책이 이미 이 PC 에 있는 사람을 위해 **폴더에서 고르기**는 「자세히」에 남겨 뒀다.
 *
 * ★ 분량표는 남긴다. 「몇 장」이 아니라 **「몇 분짜리」**로 고르는 자리이고,
 *   19장이 5분 30초로 나온 뒤에 생긴 화면이다(core/narration.py).
 */
"use strict";

import { el, api, icon, toast, debounce } from "./util.js";
import { state, invalidate } from "./store.js";
import { navigate } from "./shell.js";

export const meta = {
  title: "새 원고 만들기",
  subtitle: "단행본 한 장(章) PDF 를 끌어다 놓고, 길이를 고르면 됩니다",
};

let files = [];              // 고른 것 — {path, name, mb}. 경로는 전부 서버 안의 것
let picked = new Set();      // 고른 경로
let peeked = {};             // {경로: 미리 읽은 결과}
let plans = [];              // 목표 길이별 권장 분량 — 서버(core/narration.py)가 준다
let target = null;           // 고른 목표 길이(분)

function field(label, name, value, hint) {
  const f = el("div", "sfield");
  f.appendChild(el("label", "sfield-lb", label));
  const i = el("input");
  i.name = name;
  i.value = value == null ? "" : value;
  f.appendChild(i);
  if (hint) f.appendChild(el("div", "sfield-hint", hint));
  return f;
}

/* 파일 이름에서 책·장·이름표를 딴다. 「새뮤얼슨의경제학-5부 19장.pdf」 처럼
   사람이 이미 이름을 잘 지어 두었으므로, 빈 칸을 강요할 이유가 없다. */
function guess(name) {
  const stem = name.replace(/\.pdf$/i, "").trim();
  const parts = stem.split("-").map((s) => s.trim()).filter(Boolean);
  const book = parts.length > 1 ? parts[0] : "";
  const tail = parts.length > 1 ? parts[parts.length - 1] : stem;
  const ch = (stem.match(/(\d+)\s*장/) || [])[1] || "";
  return {
    book,
    title: ch ? `제${ch}장` : tail,
    // 이름표는 그림 파일이 매달리는 값이라 **아스키만** 쓴다. 한글이면 `ch19`.
    prefix: (book.match(/[A-Za-z]{2,6}/) || ["ch"])[0].toLowerCase() + ch,
  };
}

export function mount(root) {
  const page = el("div", "spage");
  files = []; picked = new Set(); peeked = {}; plans = []; target = null;

  // ── 1. 끌어다 놓기 ───────────────────────────────────────────────────
  const drop = el("label", "drop");
  const pick = el("input");
  pick.type = "file";
  pick.accept = ".pdf,application/pdf";
  pick.multiple = true;
  pick.hidden = true;
  // ★ **무엇을 넣는 앱인지**를 여기 적는다. 이 앱은 「단행본 작가 에이전트」고,
  //   실기책 요약이론 같은 것은 따로 만든다 — 그래서 아무 PDF 나 받는 것처럼
  //   써 두면 엉뚱한 책이 들어온다. 나가는 것도 같이 적는다: 강의 슬라이드다.
  drop.append(
    icon("upload", 30),
    el("div", "drop-big", "단행본 한 장(章) PDF 를 여기에 끌어다 놓으세요"),
    el("div", "drop-sub",
      "AI 아바타가 강의할 슬라이드 원고와 대본이 나옵니다 · "
      + "눌러서 골라도 됩니다 · 여러 장을 놓으면 원고가 여러 편 생깁니다"),
    pick);
  page.appendChild(drop);

  const listBox = el("div", "droplist");
  page.appendChild(listBox);

  const peekLine = el("div", "sfield-hint");
  page.appendChild(peekLine);

  // ── 2. 얼마나 긴 영상으로 ────────────────────────────────────────────
  const lenBox = el("div", "lentab");
  page.appendChild(lenBox);

  // ── 자세히 — **매번 답이 같은 것들.** 접어 둔다 ──────────────────────
  const more = el("details", "more");
  more.appendChild(el("summary", null, "자세히 — 버릴 쪽 · 이름 · 폴더에서 고르기"));
  const trim = el("form", "sform trim");
  trim.appendChild(field("앞에서 버릴 쪽", "drop_head", "2",
    "속표지·부제목 쪽. 아래 첫 쪽 미리보기가 본문이면 맞습니다"));
  trim.appendChild(field("뒤에서 버릴 쪽", "drop_tail", "0", "연습문제·색인 쪽. 없으면 0"));
  more.appendChild(trim);

  const form3 = el("form", "sform");
  form3.appendChild(field("책 이름", "book", "", "원고에 적힙니다"));
  form3.appendChild(field("이 장의 이름", "title", "", "원고의 h1 이 되고, 발표 표지가 됩니다"));
  form3.appendChild(field("장 예산", "slide_budget", "",
    "위에서 고른 길이가 채웁니다. 바꿔도 됩니다 — ±3장까지 넘길 수 있습니다"));
  form3.appendChild(field("이름표 앞머리", "id_prefix", "",
    "ch19 → ch19-03. 한 번 정하면 안 바꾸는 값입니다 — 그림 파일이 여기 매달립니다"));
  form3.appendChild(field("문체 주문", "tone", "", "선택 — 비워도 됩니다"));
  more.appendChild(form3);

  // 책이 이미 이 PC 에 있는 사람 — 13개를 하나씩 끌어다 놓을 이유가 없다
  const scanForm = el("form", "sform");
  scanForm.appendChild(field("폴더에서 고르기", "dir", "",
    "이 PC 에 이미 있는 PDF 폴더 경로. 올리지 않고 그 자리에서 읽습니다"));
  more.appendChild(scanForm);
  const scanBox = el("div", "pdflist");
  more.appendChild(scanBox);
  page.appendChild(more);

  // ── 실행 ─────────────────────────────────────────────────────────────
  const foot = el("div", "sfoot");
  const note = el("div", "sfoot-note", "만들기만 합니다. 돈은 안 듭니다.");
  foot.appendChild(note);
  const go = el("button", "btn primary lg");
  go.type = "button";
  go.disabled = true;
  go.append(icon("arrowRight", 15), el("span", null, "원고 만들기"));
  foot.appendChild(go);
  page.appendChild(foot);
  root.appendChild(page);

  const sync = () => { go.disabled = picked.size === 0; };

  /* ── 목표 길이 표 ──────────────────────────────────────────────────
   *
   * 숫자는 **하나도 여기서 계산하지 않는다.** 서버가 `/api/peek` 에 실어 준 것을
   * 그대로 깐다. 화면이 「15분이면 27장」이라 해 놓고 목차 프롬프트는 딴 수를
   * 받는 일이 없어야 하는데, 그것을 보장하는 유일한 방법은 계산을 한 곳에만
   * 두는 것이다(core/narration.py).
   */
  const planOf = (m) => plans.find((p) => p.minutes === m) || plans[0] || null;

  function drawPlans() {
    lenBox.innerHTML = "";
    if (!plans.length) return;           // 아직 PDF 가 없으면 표 자체가 없다

    const src = plans[0].source_chars || 0;
    lenBox.appendChild(el("div", "sfield-hint",
      `원문 ${src.toLocaleString()}자 읽음. 몇 분짜리로 만들까요 — `
      + `말하는 속도 ${plans[0].chars_per_min}자/분으로 잡은 값입니다`));

    const head = el("div", "lenrow hd");
    ["목표 길이", "요약 비율", "대본 목표", "장당 말", "슬라이드"]
      .forEach((t) => head.appendChild(el("span", null, t)));
    lenBox.appendChild(head);

    for (const p of plans) {
      const on = p.minutes === target;
      const row = el("button", "lenrow" + (on ? " on" : ""));
      row.type = "button";
      const first = el("span", "len-min");
      first.append(el("b", null, `${p.minutes}분`));
      if (p.recommended) first.appendChild(el("i", "sopt-rec", "기본"));
      row.appendChild(first);
      row.append(
        el("span", null, `${Math.round(p.ratio * 1000) / 10}%`),
        el("span", null, `${p.say_total.toLocaleString()}자`),
        el("span", null, `${p.say_per_slide}자 · ${p.seconds_per_slide}초`),
        el("span", null, `${p.slides}장`
          + (p.added_slides ? ` (원문 기준 ${p.base_slides})` : "")));
      row.onclick = () => { target = p.minutes; drawPlans(); fillBudget(); };
      lenBox.appendChild(row);
    }

    const p = planOf(target);
    // 고른 줄에 대해서만 말한다. 세 줄 다 경고를 달면 아무것도 안 읽힌다.
    for (const w of (p?.warnings || [])) lenBox.appendChild(el("div", "step-warn", w));
    lenBox.appendChild(el("div", "sfield-hint",
      `장 수는 원문이 정합니다(1,700자당 한 장). 목표가 길어지면 먼저 장마다 말을 `
      + `늘리고, 한 화면이 34초를 넘길 때만 장을 더 만듭니다. `
      + `★ 장이 늘어나는 것은 30분치까지입니다 — 60분은 30분과 같은 장 수에 `
      + `대본만 두 배입니다.`));
  }

  /* 장 예산 칸은 고른 길이가 채운다 — 사람이 손대 놓았으면 안 건드린다 */
  function fillBudget() {
    const p = planOf(target);
    if (!p) return;
    if (!touched.has("slide_budget")) form3.slide_budget.value = String(p.slides);
    const hint = form3.slide_budget.parentElement.querySelector(".sfield-hint");
    if (hint) {
      hint.textContent = `${p.minutes}분이면 ${p.slides}장 · 장마다 말 `
        + `${p.say_per_slide}자입니다. 바꿔도 됩니다 — ±3장까지 넘길 수 있습니다`;
    }
  }

  /* 고른 PDF 가 바뀌면 「자세히」 칸들을 **덮어쓴다.** 손대 놓은 칸은 안 건드린다 */
  const touched = new Set();
  for (const f of [form3.book, form3.title, form3.slide_budget, form3.id_prefix])
    f.addEventListener("input", () => touched.add(f.name));

  function fill(path) {
    const f = files.find((x) => x.path === path);
    if (!f) return;
    const g = guess(f.name);
    const pk = peeked[path];
    for (const [k, v] of Object.entries({book: g.book, title: g.title,
                                         id_prefix: g.prefix})) {
      if (!touched.has(k) && v) form3[k].value = v;
    }
    // 원문 길이가 바뀌면 표가 통째로 다시 계산된다 — 앞뒤로 버릴 쪽을 고쳐도 그렇다.
    plans = (pk && pk.length_options) || [];
    if (!plans.some((p) => p.minutes === target)) {
      target = (plans.find((p) => p.recommended) || plans[0] || {}).minutes ?? null;
    }
    drawPlans();
    fillBudget();
  }

  // ── 고른 파일 목록 ───────────────────────────────────────────────────
  function drawList() {
    listBox.innerHTML = "";
    for (const f of files) {
      const on = picked.has(f.path);
      const row = el("button", "pdfrow" + (on ? " on" : ""));
      row.type = "button";
      row.append(el("span", "pdf-name", f.name), el("span", "pdf-mb", `${f.mb}MB`));
      row.onclick = () => {
        if (on) picked.delete(f.path);
        else picked.add(f.path);
        drawList(); sync(); loadPeek();
      };
      listBox.appendChild(row);
    }
    if (picked.size > 1) {
      listBox.appendChild(el("div", "sfield-hint",
        `${picked.size}개를 골랐습니다 — 원고 ${picked.size}편이 따로 만들어집니다. `
        + "길이는 다 같이 적용되고, 이름과 장 수는 파일마다 따로 잡힙니다."));
    }
  }

  // ── 올리기 ───────────────────────────────────────────────────────────
  async function take(list) {
    const pdfs = Array.from(list).filter((f) => /\.pdf$/i.test(f.name));
    if (!pdfs.length) {
      toast("PDF 만 됩니다", "err");
      return;
    }
    drop.classList.add("busy");
    for (const f of pdfs) {
      const row = el("div", "droprow");
      row.append(el("span", "pdf-name", f.name),
                 el("span", "pdf-mb", `${(f.size / 1048576).toFixed(1)}MB 올리는 중…`));
      listBox.appendChild(row);
      try {
        // ★ api() 를 안 쓴다 — 그것은 본문을 JSON 으로 만든다. 여기는 바이트다.
        const res = await fetch(`/api/upload?name=${encodeURIComponent(f.name)}`,
                                {method: "POST", body: f});
        if (!res.ok) throw new Error(((await res.json()).detail) || res.statusText);
        const up = await res.json();
        if (!files.some((x) => x.path === up.path)) files.push(up);
        picked.add(up.path);
      } catch (e) {
        row.className = "srun-line err";
        row.textContent = `${f.name}: ${e.message || e}`;
        continue;
      }
      row.remove();
    }
    drop.classList.remove("busy");
    drawList(); sync(); loadPeek();
  }

  drop.addEventListener("click", () => pick.click());
  pick.addEventListener("change", () => { take(pick.files); pick.value = ""; });
  for (const ev of ["dragenter", "dragover"]) {
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.add("over");
    });
  }
  for (const ev of ["dragleave", "drop"]) {
    drop.addEventListener(ev, () => drop.classList.remove("over"));
  }
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    take(e.dataTransfer.files);
  });
  // 화면 아무 데나 놓아도 받는다. 브라우저가 PDF 를 **열어 버리는 것**을 막는 뜻도 있다.
  page.addEventListener("dragover", (e) => e.preventDefault());
  page.addEventListener("drop", (e) => {
    e.preventDefault();
    if (!drop.contains(e.target)) take(e.dataTransfer.files);
  });

  // ── 앞쪽 읽기 — 표를 만들 원문 글자 수가 여기서 나온다 ────────────────
  const loadPeek = debounce(async () => {
    const first = [...picked][0];
    if (!first) {
      peekLine.textContent = "";
      plans = []; drawPlans();
      return;
    }
    peekLine.textContent = "앞쪽을 읽는 중…";
    const head = parseInt(trim.drop_head.value || "0", 10) || 0;
    const tail = parseInt(trim.drop_tail.value || "0", 10) || 0;
    try {
      const r = await api(`/api/peek?path=${encodeURIComponent(first)}`
                          + `&head=${head}&tail=${tail}`);
      peeked[first] = r;
      // 미리보기는 **한 줄로 줄였다.** 확인할 것은 하나뿐이다 — 첫 쪽이 본문인가.
      const s = (r.sample || [])[0];
      peekLine.textContent =
        `${r.pages}쪽 · ${r.chars.toLocaleString()}자 · 앞 ${head}쪽을 버리고 `
        + `p.${s ? s.no : "?"} 부터: ${(s ? s.text : "").slice(0, 70)}…`;
      fill(first);
    } catch (e) {
      peekLine.textContent = "";
      listBox.appendChild(el("div", "srun-line err", String(e.message || e)));
    }
  }, 350);
  trim.drop_head.addEventListener("input", loadPeek);
  trim.drop_tail.addEventListener("input", loadPeek);

  // ── 폴더에서 고르기 (자세히 안) ──────────────────────────────────────
  const scan = async (dir) => {
    scanBox.innerHTML = "";
    if (!dir) return;
    scanBox.appendChild(el("div", "side-empty", "훑는 중…"));
    try {
      const r = await api(`/api/scan?dir=${encodeURIComponent(dir)}`);
      scanBox.innerHTML = "";
      for (const f of r.files || []) {
        const row = el("button", "pdfrow");
        row.type = "button";
        row.append(el("span", "pdf-name", f.name), el("span", "pdf-mb", `${f.mb}MB`));
        row.onclick = () => {
          if (!files.some((x) => x.path === f.path)) files.push(f);
          picked.add(f.path);
          drawList(); sync(); loadPeek();
        };
        scanBox.appendChild(row);
      }
      if (!(r.files || []).length) {
        scanBox.appendChild(el("div", "side-empty", "이 폴더에 PDF 가 없습니다."));
      }
    } catch (e) {
      scanBox.innerHTML = "";
      scanBox.appendChild(el("div", "srun-line err", String(e.message || e)));
    }
  };
  scanForm.dir.addEventListener("input",
    debounce(() => scan((scanForm.dir.value || "").trim()), 500));

  // ── 만들기 ───────────────────────────────────────────────────────────
  go.onclick = async () => {
    go.disabled = true;
    const list = files.filter((f) => picked.has(f.path));
    const head = parseInt(trim.drop_head.value || "0", 10) || 0;
    const tail = parseInt(trim.drop_tail.value || "0", 10) || 0;
    let first = null;
    try {
      for (const [i, f] of list.entries()) {
        // 첫 번째만 「자세히」에 적은 값을 쓴다. 나머지는 파일 이름에서 딴다 —
        // 여러 개를 고른 사람은 "장마다 한 편" 을 원하는 것이지, 같은 제목이
        // 붙은 여러 편을 원하는 게 아니다.
        const g = guess(f.name);
        const body = i === 0 ? {
          title: (form3.title.value || "").trim() || g.title,
          book: (form3.book.value || "").trim() || g.book,
          id_prefix: (form3.id_prefix.value || "").trim() || g.prefix,
          slide_budget: parseInt(form3.slide_budget.value || "0", 10)
                        || (planOf(target) || {}).slides || 0,
          tone: (form3.tone.value || "").trim(),
        } : {
          title: g.title, book: (form3.book.value || "").trim() || g.book,
          id_prefix: g.prefix, slide_budget: 0,
          tone: (form3.tone.value || "").trim(),
        };
        // ★ 목표 길이는 **모두에게 같이** 준다. 여러 장을 한꺼번에 고른 사람은
        //   「이 책을 15분짜리로」 를 뜻하지, 첫 장만 15분을 뜻하지 않는다.
        const p = await api("/api/projects", {
          method: "POST",
          body: {...body, pdfs: [f.path], drop_head: head, drop_tail: tail,
                 target_min: target || undefined},
        });
        if (first === null) first = p.id;
      }
      invalidate();
      state.projectId = first;
      toast(list.length > 1 ? `원고 ${list.length}편을 만들었습니다`
                            : "만들었습니다. 현황판에서 1번부터 누르세요");
      navigate("/board");
    } catch (e) {
      toast(String(e.message || e), "err");
      go.disabled = false;
    }
  };
}
