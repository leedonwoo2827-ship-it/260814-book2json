/* 원고를 **진짜 브라우저에 띄워 재는** 자. b7-check 가 부른다.
 *
 *     node tools/measure.mjs <원고.html> [--width 960] [--box 507] [--max-blocks 6]
 *     → stdout 으로 JSON 하나
 *
 * ★ 왜 재는가. 규약의 숫자가 전부 픽셀이기 때문이다(944 × 507). 「여섯 줄 이내로
 *   썼으니 들어갈 것이다」 는 추측이고, 실제로는 표 한 칸이 두 줄로 접히거나
 *   SVG 가 생각보다 커서 넘친다. 넘친 장은 발표 쇼케이스에서 **그 장만 통째로
 *   축소되고**, 장을 넘길 때마다 글자 크기가 들쭉날쭉해진다. 이쪽에서 안 재면
 *   저쪽에서 발표 직전에 안다.
 *
 * ★ 끊는 자리를 `260812-summary-shocase/tools/split_sections.mjs` 와 **똑같이**
 *   맞춘다. 저쪽은 제목(h3, h3 가 없는 h2)을 찾고 **그다음 형제부터 다음 제목
 *   직전까지**를 그 장의 몸통으로 가져간다. 여기서 다르게 끊으면 여기서 잰 높이가
 *   저기서 나올 높이와 달라져서, 재는 의미가 없어진다.
 *
 * ★ 폭 960 의 근거: 저쪽은 원본을 960px 뷰포트에서 렌더한다. UA 기본값
 *   `body{margin:8px}` 이 좌우로 8px 씩 먹어서 body 테두리 상자가 **944px** 이 되고,
 *   그 944 가 1536px 상자로 확대된다. 그래서 **배치가 944 에서 일어나야** 줄바꿈
 *   위치가 같다. 여기서 폭을 바꾸면 잰 값이 저쪽과 어긋난다.
 */
import { chromium } from "playwright";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : d; };
const src = argv.find((a) => !a.startsWith("--"));
if (!src) {
  console.error("사용법: node tools/measure.mjs <원고.html> [--width 960] [--box 507]");
  process.exit(2);
}

const SRC = resolve(src);
const WIDTH = parseInt(opt("--width", "960"), 10);
const BOX_H = parseInt(opt("--box", "507"), 10);
const MAX_BLOCKS = parseInt(opt("--max-blocks", "6"), 10);

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: WIDTH, height: 1200 });
await page.goto(pathToFileURL(SRC).href, { waitUntil: "load" });

/* 문서 전체 높이만큼 뷰포트를 키운다 — 스크롤 없이 좌표가 페이지 좌표와 맞아야
   "한 화면에 들어가는가" 판단이 저쪽과 같은 결과를 낸다. */
const full = await page.evaluate(() => document.documentElement.scrollHeight);
await page.setViewportSize({ width: WIDTH, height: Math.ceil(full) + 40 });

const report = await page.evaluate(({ BOX_H, MAX_BLOCKS }) => {
  /* ★ `tagName` 을 반드시 소문자로 내려서 본다. 인라인 SVG 는 HTML 요소가 아니라
     **대소문자를 그대로 지키는** SVG 요소라 `tagName` 이 `"svg"` 다(`"SVG"` 가
     아니다). 예전에 `=== "SVG"` 로 비교했더니 스물세 장에 그림이 다 들어 있는데도
     전부 "그림도 표도 없음" 으로 잡혔다 — 검사기가 조용히 거짓말을 했다. */
  const tag = (el) => (el.tagName || "").toLowerCase();

  /* 줄 세기 — 규약과 같다. li·p 하나가 한 줄, 표는 tr 하나가 한 줄, svg 는 통째로 한 줄. */
  const countLines = (els) => {
    let n = 0;
    for (const el of els) {
      const t = tag(el);
      if (t === "table") n += el.querySelectorAll("tr").length || 1;
      else if (t === "ul" || t === "ol") n += el.querySelectorAll("li").length;
      else n += 1;
    }
    return n;
  };

  const heads = [...document.querySelectorAll("h2, h3")];
  /* h3 가 하나도 없는 h2 는 그 h2 자체가 장이다(규약 2-2). 뒤에 h3 가 오면 묶음이다. */
  const isSlide = (h, i) =>
    tag(h) === "h3" || !(heads[i + 1] && tag(heads[i + 1]) === "h3");

  const out = [];
  for (let i = 0; i < heads.length; i++) {
    const h = heads[i];
    if (!isSlide(h, i)) continue;

    /* ★ 화면에 안 뜨는 형제는 몸통이 아니다. 원고 끝에 기계용
       `<script type="application/json" id="imgprompts">` 를 하나 넣어 두는데,
       그것이 마지막 장의 다음 형제라 **마지막 장만 한 줄 더 세어졌다**
       (split_sections 는 4줄, 여기는 5줄). 눈에 안 보이는 한 줄이라 사람이
       알아챌 방법이 없었다 — 세는 자리에서 막는다. */
    const SKIP = new Set(["script", "style", "template", "link", "meta"]);
    const body = [];
    for (let el = h.nextElementSibling; el && !/^h[123]$/.test(tag(el));
         el = el.nextElementSibling) {
      if (!SKIP.has(tag(el))) body.push(el);
    }

    /* 몸통의 세로 크기 — 첫 요소 위부터 마지막 요소 아래까지. 여백은 빼고 잰다
       (저쪽이 조각을 오려 낼 때 첫 줄·끝 줄의 바깥 여백을 걷어 내기 때문이다). */
    let height = 0;
    if (body.length) {
      const top = body[0].getBoundingClientRect().top;
      const bottom = body[body.length - 1].getBoundingClientRect().bottom;
      height = Math.round(bottom - top);
    }

    const lines = countLines(body);
    const svg = body.some((e) => tag(e) === "svg" || e.querySelector?.("svg"));
    const table = body.some((e) => tag(e) === "table" || e.querySelector?.("table"));

    out.push({
      id: h.dataset.id || "",
      title: (h.textContent || "").trim().slice(0, 60),
      height, lines, svg, table,
      /* ★ 있는지(true/false)가 아니라 **몇 자인지**를 낸다. 영상 길이를 정하는 것이
         이 글자 수라, 개수만 세면 「data-say 27/27」 이라 적어 놓고도 5분 30초짜리인
         것을 모른다(2026-08-14). 공백은 뺀다 — core/narration.py 와 같은 셈법이다. */
      say: (h.dataset.say || "").replace(/\s+/g, "").length,
      img: !!h.dataset.img,
      over: height > BOX_H,
      longer: lines > MAX_BLOCKS,
      empty: body.length === 0,
      bare: !svg && !table,
    });
  }

  /* 가로로 밀렸는가 — 규약의 마지막 방어선. 밀리면 캡처가 못 쓰게 된다. */
  const wide = document.documentElement.scrollWidth > document.documentElement.clientWidth;

  /* 표지·마무리 대본은 h1 에 붙어 있다. 장이 아니라서 위 목록에는 안 들어가지만
     **소리는 나므로** 길이에는 들어가야 한다. */
  const h1 = document.querySelector("h1");
  const len = (s) => (s || "").replace(/\s+/g, "").length;
  return {
    slides: out, wide,
    intro: len(h1?.dataset.say), outro: len(h1?.dataset.outroSay),
  };
}, { BOX_H, MAX_BLOCKS });

await browser.close();
process.stdout.write(JSON.stringify(report));
