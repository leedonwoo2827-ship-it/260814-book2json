/* 새 원고 만들기 — **책이 어디 있는지 넣고, 앞뒤 몇 쪽을 버릴지 눈으로 정한다.**
 *
 * 패널이 아니라 바닥에 두는 이유는 규칙 때문이다: **입력창이 있는 화면은 패널에
 * 두지 않는다.** 패널은 Esc 나 스크림 클릭으로 닫히므로, 경로를 타이핑하다 한 번만
 * 잘못 눌러도 날아간다.
 *
 * ★ PDF 를 업로드가 아니라 **폴더 경로**로 받는다. 13개 × 평균 9MB 를 base64 로
 *   올리면 브라우저가 버틴다는 보장이 없고, 무엇보다 책은 이미 이 PC 에 있다.
 *   발표 쇼케이스가 화면녹화 폴더를 받는 방식과 같다.
 *
 * ★ 「앞에서 버릴 쪽」을 자동으로 알아내지 않는다. 속표지가 몇 장인지는 책마다
 *   다르고, 틀리면 본문 첫 쪽이 조용히 사라진다. 미리보기로 **보고** 정하게 한다.
 */
"use strict";

import { el, api, icon, toast, debounce } from "./util.js";
import { state, invalidate } from "./store.js";
import { navigate } from "./shell.js";

export const meta = {
  title: "새 원고 만들기",
  subtitle: "책이 어디 있는지 넣으면, 읽어 보고 목차를 세울 것을 만듭니다",
};

let picked = new Set();      // 고른 PDF 경로
let files = [];              // 스캔 결과

function sec(n, title, sub) {
  const s = el("div", "ssec");
  const hd = el("div", "ssec-hd");
  hd.append(el("i", "ssec-n", String(n)), el("h3", null, title));
  if (sub) hd.appendChild(el("span", "ssec-sub", sub));
  s.appendChild(hd);
  return s;
}

function field(label, name, ph, hint, value) {
  const f = el("div", "sfield");
  f.appendChild(el("label", "sfield-lb", label));
  const i = el("input");
  i.name = name;
  i.placeholder = ph || "";
  if (value != null) i.value = value;
  f.appendChild(i);
  if (hint) f.appendChild(el("div", "sfield-hint", hint));
  return f;
}

export function mount(root) {
  const page = el("div", "spage");
  picked = new Set();
  files = [];

  // ── 1. 책이 어디 있나 ────────────────────────────────────────────────
  const s1 = sec(1, "책", "PDF 가 어디 있는지");
  const form = el("form", "sform");
  form.appendChild(field("책 이름", "book", "예: 새뮤얼슨의 경제학",
    "원고에 적힙니다. 비워도 됩니다"));
  form.appendChild(field("PDF 폴더", "dir", "D:\\00work\\260814-book2json\\_contex",
    "폴더 안의 PDF 를 훑어 목록으로 보여 줍니다"));
  s1.appendChild(form);

  const listBox = el("div", "pdflist");
  listBox.appendChild(el("div", "side-empty", "폴더 경로를 넣으면 목록이 나옵니다."));
  s1.appendChild(listBox);
  page.appendChild(s1);

  // ── 2. 어디부터 본문인가 ────────────────────────────────────────────
  const s2 = sec(2, "본문이 시작하는 곳", "속표지를 몇 장 버릴지");
  const trim = el("form", "sform trim");
  trim.appendChild(field("앞에서 버릴 쪽", "drop_head", "2",
    "속표지·부제목 쪽. 아래 미리보기를 보고 정하세요", "2"));
  trim.appendChild(field("뒤에서 버릴 쪽", "drop_tail", "0",
    "연습문제·색인 쪽. 없으면 0", "0"));
  s2.appendChild(trim);
  const peek = el("div", "peek");
  peek.appendChild(el("div", "side-empty", "PDF 를 하나 고르면 첫 쪽들을 보여 줍니다."));
  s2.appendChild(peek);
  page.appendChild(s2);

  // ── 3. 몇 장으로 ─────────────────────────────────────────────────────
  const s3 = sec(3, "장 수와 이름표", "h3 하나 = 슬라이드 한 판");
  const form3 = el("form", "sform");
  form3.appendChild(field("이 장의 이름", "title", "비우면 PDF 이름에서 따옵니다",
    "원고의 h1 이 되고, 발표 표지가 됩니다"));
  form3.appendChild(field("장 예산", "slide_budget", "40",
    "만들 슬라이드 수. ±3장까지 넘길 수 있습니다. 적게 시작하는 편이 낫습니다 — "
    + "장마다 문구와 그림을 사람이 확인합니다", "40"));
  form3.appendChild(field("이름표 앞머리", "id_prefix", "비우면 이름에서 딴 값",
    "sam → sam-03. 한 번 정하면 안 바꾸는 값입니다 — 그림 파일이 여기 매달립니다"));
  form3.appendChild(field("문체 주문", "tone", "선택 — 예: 시험 대비용으로 정의를 또렷하게",
    "비워도 됩니다"));
  s3.appendChild(form3);
  page.appendChild(s3);

  // ── 실행 ─────────────────────────────────────────────────────────────
  const foot = el("div", "sfoot");
  const note = el("div", "sfoot-note",
    "만들기만 합니다. 책을 읽는 것은 다음 화면에서 눌러야 시작합니다 — 돈은 안 듭니다.");
  foot.appendChild(note);
  const go = el("button", "btn primary lg");
  go.type = "button";
  go.disabled = true;
  go.append(icon("arrowRight", 15), el("span", null, "원고 만들기"));
  foot.appendChild(go);
  page.appendChild(foot);

  // ── 폴더 훑기 ────────────────────────────────────────────────────────
  const drawList = () => {
    listBox.innerHTML = "";
    if (!files.length) {
      listBox.appendChild(el("div", "side-empty", "이 폴더에 PDF 가 없습니다."));
      return;
    }
    const all = el("button", "sopt" + (picked.size === files.length ? " on" : ""));
    all.type = "button";
    all.textContent = picked.size === files.length ? "전부 해제" : "전부 고르기";
    all.onclick = () => {
      if (picked.size === files.length) picked.clear();
      else files.forEach((f) => picked.add(f.path));
      drawList();
      syncGo();
    };
    listBox.appendChild(all);

    for (const f of files) {
      const row = el("button", "pdfrow" + (picked.has(f.path) ? " on" : ""));
      row.type = "button";
      row.append(el("span", "pdf-name", f.name), el("span", "pdf-mb", `${f.mb}MB`));
      row.onclick = () => {
        if (picked.has(f.path)) picked.delete(f.path);
        else picked.add(f.path);
        drawList();
        syncGo();
        loadPeek();
      };
      listBox.appendChild(row);
    }
    const n = picked.size;
    listBox.appendChild(el("div", "sfield-hint",
      n ? `${n}개를 골랐습니다. 한 원고가 됩니다 — 장이 여럿이면 따로 만드세요.`
        : "하나 이상 고르세요."));
  };

  const syncGo = () => { go.disabled = picked.size === 0; };

  const scan = debounce(async () => {
    const dir = (form.dir.value || "").trim();
    if (!dir) return;
    listBox.innerHTML = "";
    listBox.appendChild(el("div", "side-empty", "훑는 중…"));
    try {
      const r = await api(`/api/scan?dir=${encodeURIComponent(dir)}`);
      files = r.files || [];
      picked = new Set();
      drawList();
      syncGo();
    } catch (e) {
      listBox.innerHTML = "";
      listBox.appendChild(el("div", "srun-line err", String(e.message || e)));
    }
  }, 500);
  form.dir.addEventListener("input", scan);

  // ── 앞쪽 미리보기 ────────────────────────────────────────────────────
  const loadPeek = debounce(async () => {
    const first = [...picked][0];
    peek.innerHTML = "";
    if (!first) {
      peek.appendChild(el("div", "side-empty", "PDF 를 하나 고르면 첫 쪽들을 보여 줍니다."));
      return;
    }
    peek.appendChild(el("div", "side-empty", "읽는 중…"));
    const head = parseInt(trim.drop_head.value || "0", 10) || 0;
    const tail = parseInt(trim.drop_tail.value || "0", 10) || 0;
    try {
      const r = await api(`/api/peek?path=${encodeURIComponent(first)}`
                          + `&head=${head}&tail=${tail}`);
      peek.innerHTML = "";
      peek.appendChild(el("div", "sfield-hint",
        `${r.pages}쪽 · ${r.chars.toLocaleString()}자 · 본문 ${r.body_size}pt`
        + ` · 제목 ${r.heads.length}개`));
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
    } catch (e) {
      peek.innerHTML = "";
      peek.appendChild(el("div", "srun-line err", String(e.message || e)));
    }
  }, 400);
  trim.drop_head.addEventListener("input", loadPeek);
  trim.drop_tail.addEventListener("input", loadPeek);

  // ── 만들기 ───────────────────────────────────────────────────────────
  go.onclick = async () => {
    go.disabled = true;
    try {
      const p = await api("/api/projects", {
        method: "POST",
        body: {
          title: (form3.title.value || "").trim() || null,
          book: (form.book.value || "").trim(),
          pdfs: [...picked],
          id_prefix: (form3.id_prefix.value || "").trim() || null,
          slide_budget: parseInt(form3.slide_budget.value || "40", 10) || 40,
          drop_head: parseInt(trim.drop_head.value || "0", 10) || 0,
          drop_tail: parseInt(trim.drop_tail.value || "0", 10) || 0,
          tone: (form3.tone.value || "").trim(),
        },
      });
      invalidate();
      state.projectId = p.id;
      toast("만들었습니다. 현황판에서 1번부터 누르세요");
      navigate("/board");
    } catch (e) {
      toast(String(e.message || e), "err");
      go.disabled = false;
    }
  };

  root.appendChild(page);
}
