/* 새 원고 만들기 — **넣을 것은 PDF 하나뿐. 나머지는 채워 둔다.**
 *
 * 패널이 아니라 바닥에 두는 이유는 규칙 때문이다: **입력창이 있는 화면은 패널에
 * 두지 않는다.** 패널은 Esc 나 스크림 클릭으로 닫히므로, 경로를 타이핑하다 한 번만
 * 잘못 눌러도 날아간다.
 *
 * ★ PDF 를 업로드가 아니라 **폴더 경로**로 받는다. 13개 × 평균 9MB 를 base64 로
 *   올리면 브라우저가 버틴다는 보장이 없고, 무엇보다 책은 이미 이 PC 에 있다.
 *
 * ★ **placeholder 로는 아무것도 시작되지 않는다.** 예전엔 폴더 칸을 비운 채 회색
 *   글씨로 예시 경로만 보여 줬는데, 그 글씨가 값처럼 보여서 사람이 다 채웠다고
 *   여기고 넘어갔다 — 목록은 영영 안 나왔다(2026-08-14 신고: "새로운 원고 넣으면
 *   아무것도 안 나옵니다"). 지금은 서버가 추천한 폴더를 **값으로 넣고**, 화면이
 *   뜨자마자 훑고, 첫 PDF 를 골라 두고, 앞쪽을 미리 읽어 둔다.
 *   사람이 할 일은 **다른 PDF 를 고르는 것과 단추를 누르는 것**뿐이다.
 *
 * ★ 물어보는 것은 넷뿐이고 넷 다 **권장값이 이미 들어 있다.** 열 개를 물으면
 *   아무도 안 채운다. 바꿔야 할 사람만 바꾸면 된다.
 */
"use strict";

import { el, api, icon, toast, debounce } from "./util.js";
import { state, invalidate } from "./store.js";
import { navigate } from "./shell.js";

export const meta = {
  title: "새 원고 만들기",
  subtitle: "PDF 를 고르고 단추를 누르면 됩니다. 나머지는 채워 두었습니다",
};

/* 한 장(章)에 몇 자당 슬라이드 하나인가. 새뮤얼슨 19·20장 실측에서 나온 값이다
   (44,093자 → 27장 · 51,234자 → 28장). 이 값으로 장 예산을 추천한다. */
const CHARS_PER_SLIDE = 1700;

let files = [];              // 훑어 온 PDF 목록
let picked = new Set();      // 고른 경로
let peeked = {};             // {경로: 미리 읽은 결과}

function sec(n, title, sub) {
  const s = el("div", "ssec");
  const hd = el("div", "ssec-hd");
  hd.append(el("i", "ssec-n", String(n)), el("h3", null, title));
  if (sub) hd.appendChild(el("span", "ssec-sub", sub));
  s.appendChild(hd);
  return s;
}

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
  files = []; picked = new Set(); peeked = {};

  // ── 1. 책 ────────────────────────────────────────────────────────────
  const s1 = sec(1, "책", "PDF 가 어디 있는지");
  const form = el("form", "sform");
  form.appendChild(field("PDF 폴더", "dir", "", "훑는 중…"));
  s1.appendChild(form);
  const listBox = el("div", "pdflist");
  s1.appendChild(listBox);
  page.appendChild(s1);

  // ── 2. 본문이 시작하는 곳 ────────────────────────────────────────────
  const s2 = sec(2, "본문이 시작하는 곳", "속표지를 몇 장 버릴지");
  const trim = el("form", "sform trim");
  trim.appendChild(field("앞에서 버릴 쪽", "drop_head", "2",
    "속표지·부제목 쪽. 아래 미리보기의 첫 쪽이 본문이면 맞습니다"));
  trim.appendChild(field("뒤에서 버릴 쪽", "drop_tail", "0",
    "연습문제·색인 쪽. 없으면 0"));
  s2.appendChild(trim);
  const peek = el("div", "peek");
  s2.appendChild(peek);
  page.appendChild(s2);

  // ── 3. 이름과 장 수 ──────────────────────────────────────────────────
  const s3 = sec(3, "이름과 장 수", "h3 하나 = 슬라이드 한 판");
  const form3 = el("form", "sform");
  form3.appendChild(field("책 이름", "book", "", "원고에 적힙니다"));
  form3.appendChild(field("이 장의 이름", "title", "",
    "원고의 h1 이 되고, 발표 표지가 됩니다"));
  form3.appendChild(field("장 예산", "slide_budget", "",
    "만들 슬라이드 수. ±3장까지 넘길 수 있습니다"));
  form3.appendChild(field("이름표 앞머리", "id_prefix", "",
    "ch19 → ch19-03. 한 번 정하면 안 바꾸는 값입니다 — 그림 파일이 여기 매달립니다"));
  form3.appendChild(field("문체 주문", "tone", "", "선택 — 비워도 됩니다"));
  s3.appendChild(form3);
  page.appendChild(s3);

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

  const budgetOf = (chars) =>
    Math.max(12, Math.min(45, Math.round((chars || 0) / CHARS_PER_SLIDE)));

  /* 고른 PDF 가 바뀌면 아래 칸들을 **덮어쓴다.** 단, 사람이 손대 놓은 칸은 안 건드린다 */
  const touched = new Set();
  for (const f of [form3.book, form3.title, form3.slide_budget, form3.id_prefix])
    f.addEventListener("input", () => touched.add(f.name));

  function fill(path) {
    const f = files.find((x) => x.path === path);
    if (!f) return;
    const g = guess(f.name);
    const pk = peeked[path];
    const vals = {
      book: g.book, title: g.title, id_prefix: g.prefix,
      slide_budget: pk ? String(budgetOf(pk.chars)) : "",
    };
    for (const [k, v] of Object.entries(vals)) {
      if (!touched.has(k) && v) form3[k].value = v;
    }
    const hint = form3.slide_budget.parentElement.querySelector(".sfield-hint");
    if (pk && hint) {
      hint.textContent = `권장 ${budgetOf(pk.chars)}장 — 본문 `
        + `${pk.chars.toLocaleString()}자를 ${CHARS_PER_SLIDE}자에 한 장씩으로 잡은 값입니다`
        + " (19·20장 실측에서 나온 비율). 적게 시작하는 편이 낫습니다";
    }
  }

  function drawList() {
    listBox.innerHTML = "";
    if (!files.length) {
      listBox.appendChild(el("div", "side-empty",
        "이 폴더에 PDF 가 없습니다. 위 경로를 고쳐 보세요."));
      return;
    }
    files.forEach((f, i) => {
      const on = picked.has(f.path);
      const row = el("button", "pdfrow" + (on ? " on" : ""));
      row.type = "button";
      row.append(el("span", "pdf-name", f.name), el("span", "pdf-mb", `${f.mb}MB`));
      if (i === 0) row.appendChild(el("i", "sopt-rec", "권장"));
      row.onclick = () => {
        if (on) picked.delete(f.path);
        else picked.add(f.path);
        drawList();
        sync();
        loadPeek();
      };
      listBox.appendChild(row);
    });
    const n = picked.size;
    listBox.appendChild(el("div", "sfield-hint",
      n <= 1 ? "PDF 한 개가 원고 한 편이 됩니다."
             : `${n}개를 골랐습니다 — 원고 ${n}편이 따로 만들어집니다. `
               + "아래 이름·장 수는 첫 번째 것에만 쓰이고, 나머지는 파일 이름에서 땁니다."));
  }

  const sync = () => { go.disabled = picked.size === 0; };

  const scan = async (dir) => {
    listBox.innerHTML = "";
    listBox.appendChild(el("div", "side-empty", "훑는 중…"));
    try {
      const r = await api(`/api/scan?dir=${encodeURIComponent(dir)}`);
      files = r.files || [];
      // ★ 첫 PDF 를 **미리 골라 둔다.** 고를 것이 하나뿐인 화면에서 "고르세요" 만
      //   띄우면 한 걸음이 그냥 늘어난다. 다른 것을 원하면 눌러서 바꾸면 된다.
      picked = new Set(files.length ? [files[0].path] : []);
      drawList();
      sync();
      loadPeek();
      const hint = form.dir.parentElement.querySelector(".sfield-hint");
      if (hint) hint.textContent = `${files.length}개를 찾았습니다`;
    } catch (e) {
      files = []; picked = new Set();
      listBox.innerHTML = "";
      listBox.appendChild(el("div", "srun-line err", String(e.message || e)));
      sync();
    }
  };
  form.dir.addEventListener("input", debounce(
    () => scan((form.dir.value || "").trim()), 500));

  const loadPeek = debounce(async () => {
    const first = [...picked][0];
    peek.innerHTML = "";
    if (!first) return;
    peek.appendChild(el("div", "side-empty", "앞쪽을 읽는 중…"));
    const head = parseInt(trim.drop_head.value || "0", 10) || 0;
    const tail = parseInt(trim.drop_tail.value || "0", 10) || 0;
    try {
      const r = await api(`/api/peek?path=${encodeURIComponent(first)}`
                          + `&head=${head}&tail=${tail}`);
      peeked[first] = r;
      peek.innerHTML = "";
      peek.appendChild(el("div", "sfield-hint",
        `${r.pages}쪽 · ${r.chars.toLocaleString()}자 · 본문 ${r.body_size}pt`
        + ` · 책이 매긴 제목 ${r.heads.length}개`));
      for (const s of r.sample || []) {
        const b = el("div", "peek-page");
        b.append(el("span", "peek-no", `p.${s.no}`),
                 el("span", "peek-txt", s.text || "(빈 쪽)"));
        peek.appendChild(b);
      }
      if (r.heads?.length) {
        const h = el("div", "peek-heads");
        for (const x of r.heads.slice(0, 12)) {
          h.appendChild(el("div", "peek-head",
            "  ".repeat(Math.max(0, x.level - 1))
            + (x.num ? x.num + ". " : "") + x.title + `  (p.${x.page})`));
        }
        peek.appendChild(h);
      } else {
        peek.appendChild(el("div", "srun-line",
          "책에서 제목을 못 찾았습니다. 목차는 본문만 보고 세웁니다 — 그래도 됩니다."));
      }
      fill(first);
    } catch (e) {
      peek.innerHTML = "";
      peek.appendChild(el("div", "srun-line err", String(e.message || e)));
    }
  }, 350);
  trim.drop_head.addEventListener("input", loadPeek);
  trim.drop_tail.addEventListener("input", loadPeek);

  // ── 만들기 ───────────────────────────────────────────────────────────
  go.onclick = async () => {
    go.disabled = true;
    const list = files.filter((f) => picked.has(f.path));
    const head = parseInt(trim.drop_head.value || "0", 10) || 0;
    const tail = parseInt(trim.drop_tail.value || "0", 10) || 0;
    let first = null;
    try {
      for (const [i, f] of list.entries()) {
        // 첫 번째만 화면에 적은 값을 쓴다. 나머지는 파일 이름에서 딴다 —
        // 여러 개를 고른 사람은 "장마다 한 편" 을 원하는 것이지, 같은 제목이
        // 붙은 여러 편을 원하는 게 아니다.
        const g = guess(f.name);
        const body = i === 0 ? {
          title: (form3.title.value || "").trim() || g.title,
          book: (form3.book.value || "").trim() || g.book,
          id_prefix: (form3.id_prefix.value || "").trim() || g.prefix,
          slide_budget: parseInt(form3.slide_budget.value || "0", 10)
                        || budgetOf((peeked[f.path] || {}).chars),
          tone: (form3.tone.value || "").trim(),
        } : {
          title: g.title, book: (form3.book.value || "").trim() || g.book,
          id_prefix: g.prefix, slide_budget: 0,
          tone: (form3.tone.value || "").trim(),
        };
        const p = await api("/api/projects", {
          method: "POST",
          body: {...body, pdfs: [f.path], drop_head: head, drop_tail: tail,
                 slide_budget: body.slide_budget || 30},
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

  // ── 화면이 뜨자마자 ──────────────────────────────────────────────────
  (async () => {
    let dir = "";
    try {
      dir = (await api("/api/settings")).suggest_pdf_dir || "";
    } catch { /* 서버가 아직 안 떴을 수 있다 */ }
    form.dir.value = dir;
    if (dir) scan(dir);
    else {
      listBox.appendChild(el("div", "side-empty",
        "PDF 가 든 폴더 경로를 위에 넣으세요."));
      const hint = form.dir.parentElement.querySelector(".sfield-hint");
      if (hint) hint.textContent = "예: D:\\00work\\260814-book2json\\_contex";
    }
  })();
}
