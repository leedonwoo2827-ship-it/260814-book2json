/* 원고 — **944 × 507 자 위에 얹어 본다.**
 *
 * 이 화면의 목적은 하나다. 「여섯 줄 이내로 썼다」 는 말이 아니라 **실제로 한 화면에
 * 들어가는가**를 눈으로 보는 것. 규약의 숫자가 전부 픽셀이라, 숫자를 세는 것으로는
 * 알 수 없다 — 표 한 칸이 두 줄로 접히거나 SVG 가 생각보다 커서 넘친다.
 *
 * ★ 미리보기는 조립된 원고(`/preview/{pid}`)를 iframe 으로 그대로 문다. 화면이
 *   따로 그리면 그 화면에서만 맞는 그림이 된다 — 실제로 나가는 파일을 봐야 한다.
 *
 * ★ 폭 960 으로 띄운 뒤 CSS 로 줄인다. 960 인 이유: UA 기본값 `body{margin:8px}` 이
 *   좌우로 8px 씩 먹어서 배치 폭이 **944** 가 된다. 발표 쇼케이스가 원고를 오릴 때
 *   쓰는 폭이 그것이라, 여기서 폭을 바꾸면 보이는 줄바꿈이 실제와 달라진다.
 */
"use strict";

import { el, api, icon, toast } from "./util.js";
import { state, guard } from "./store.js";
import { navigate } from "./shell.js";

export const meta = {
  title: "원고",
  subtitle: "장마다 한 화면(944 × 507)에 들어가는지 자 위에서 봅니다",
};

const BOX_W = 944, BOX_H = 507, VIEW_W = 960;

const FLAG_TXT = {
  over: "한 화면을 넘침 — h3 를 하나 더 만들어 나누세요",
  longer: "줄이 많음 — 여섯 줄 안쪽으로",
  empty: "몸통 없음 — 3번을 다시 돌리세요",
  bare: "그림도 표도 없음 — 3번을 다시 돌리세요",
};

export async function mount(root) {
  if (!guard(root)) return;
  const page = el("div", "dpage");
  root.appendChild(page);
  page.appendChild(el("div", "side-empty", "읽는 중…"));

  let doc;
  try {
    doc = await api(`/api/projects/${state.projectId}/outline`);
  } catch (e) {
    page.innerHTML = "";
    page.appendChild(el("div", "srun-line err", String(e.message || e)));
    return;
  }
  page.innerHTML = "";

  const written = (doc.slides || []).filter((s) => (s.blocks || []).length);
  if (!written.length) {
    page.appendChild(el("div", "side-empty",
      "아직 몸통이 없습니다. 현황판에서 3번 「몸통 쓰기」를 누르세요."));
    return;
  }

  // ── 왼쪽: 장 목록 · 오른쪽: 미리보기 ──────────────────────────────────
  const split = el("div", "dsplit");
  const side = el("div", "dside");
  const main = el("div", "dmain");
  split.append(side, main);
  page.appendChild(split);

  const bad = written.filter((s) => (s.flags || []).length);
  const bar = el("div", "obar");
  bar.append(el("span", "ostat", `${written.length}장`),
             el("span", "ostat",
                `줄 ${written.reduce((a, s) => a + (s.lines || 0), 0)}개`),
             el("span", "ostat" + (bad.length ? " warn" : ""),
                bad.length ? `어긋난 장 ${bad.length}개` : "규약에 어긋난 장 없음"));
  side.appendChild(bar);

  if (!written.some((s) => s.height)) {
    side.appendChild(el("div", "sfield-hint",
      "아직 안 재 봤습니다. 현황판 5번 「조립하고 재기」를 누르면 높이가 채워집니다."));
  }

  const frame = el("iframe", "dframe");
  frame.src = `/preview/${state.projectId}`;
  frame.title = "원고 미리보기";
  const stage = el("div", "dstage");
  const ruler = el("div", "druler");
  ruler.appendChild(el("span", "druler-lb", `한 화면 ${BOX_W} × ${BOX_H}`));
  stage.append(frame, ruler);
  main.appendChild(stage);
  main.appendChild(el("div", "sfield-hint",
    "붉은 선이 한 화면의 아래끝입니다. 장의 몸통이 이 선을 넘으면 발표에서 그 장만 축소됩니다."));

  /* 폭 960 으로 띄우고 통째로 줄인다. 안을 반응형으로 만들지 않는다 —
     반응형이면 여기서 보이는 줄바꿈이 실제로 나가는 것과 달라진다. */
  const fit = () => {
    const w = stage.clientWidth || VIEW_W;
    const k = Math.min(1, w / VIEW_W);
    frame.style.width = `${VIEW_W}px`;
    frame.style.transform = `scale(${k})`;
    stage.style.setProperty("--k", String(k));
  };
  addEventListener("resize", fit);
  setTimeout(fit, 60);

  for (const s of written) {
    const row = el("button", "drow" + ((s.flags || []).length ? " bad" : ""));
    row.type = "button";
    row.append(el("span", "oid", s.data_id),
               el("span", "drow-t", s.title || ""),
               el("span", "ostat", `${s.lines}줄`));
    if (s.height) row.appendChild(
      el("span", "ostat" + (s.height > BOX_H ? " warn" : ""), `${s.height}px`));
    for (const f of s.flags || [])
      row.title = (row.title ? row.title + "\n" : "") + (FLAG_TXT[f] || f);

    row.onclick = () => {
      // iframe 안의 그 장으로 굴린다. 같은 출처라 안을 만질 수 있다.
      try {
        const d = frame.contentDocument;
        const h = d?.querySelector(`[data-id="${CSS.escape(s.data_id)}"]`);
        if (h) h.scrollIntoView({behavior: "smooth", block: "start"});
      } catch { /* 아직 안 떴다 */ }
      side.querySelectorAll(".drow").forEach((x) => x.classList.remove("on"));
      row.classList.add("on");
    };
    side.appendChild(row);
  }

  if (bad.length) {
    const box = el("div", "card");
    box.appendChild(el("div", "card-title", `규약에 어긋난 장 ${bad.length}개`));
    const b = el("div", "card-body");
    for (const s of bad.slice(0, 20)) {
      b.appendChild(el("div", "rule-row",
        `${s.data_id} ${s.title || ""} — ${(s.flags || [])
          .map((f) => FLAG_TXT[f] || f).join(" · ")}`));
    }
    box.appendChild(b);
    side.appendChild(box);
  }
}
