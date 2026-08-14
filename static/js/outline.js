/* 목차 — **h3 하나 = 슬라이드 한 판. 여기서 정한 장 수가 곧 발표 장 수다.**
 *
 * 고칠 수 있는 것은 제목·말할 것·그림 종류·줄 예산이고, 뺄 수도 있다.
 * 고친 것은 `outline.overrides.json` 에 이름표(`data_id`)를 키로 쌓인다 —
 * b2 를 다시 돌려도 살아남는다.
 *
 * ★ 배열이 아니라 **이름표를 키로 하는 dict** 로 보낸다. 배열이면 제목 하나를
 *   고쳐도 나머지 전부를 같이 보내야 하고, 그 사이에 장이 바뀌면 남의 값을 덮어쓴다.
 *
 * ★ 이름표는 **화면에 보이되 못 고친다.** 그림 파일이 여기 매달려 있어서, 고치는
 *   순간 이미 그려 둔 그림이 미아가 된다. 보여 주는 이유는 이미지 화면·이름바꾸기
 *   표와 눈으로 이어야 하기 때문이다.
 */
"use strict";

import { el, api, icon, toast, debounce } from "./util.js";
import { state, invalidateStages, guard } from "./store.js";
import { navigate } from "./shell.js";

export const meta = {
  title: "목차",
  subtitle: "h3 하나가 슬라이드 한 판입니다. 여기서 확정한 뒤에 비싼 단계가 돕니다",
};

const FLAG_TXT = {
  over: "한 화면을 넘침", longer: "줄이 많음",
  empty: "몸통 없음", bare: "그림도 표도 없음",
};

export async function mount(root) {
  if (!guard(root)) return;
  const page = el("div", "opage");
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

  if (!doc.ready) {
    page.appendChild(el("div", "side-empty",
      "아직 목차가 없습니다. 현황판에서 2번 「장 나누기」를 누르세요."));
    return;
  }

  const patch = {slides: {}, dropped: []};
  const save = debounce(async () => {
    if (!Object.keys(patch.slides).length && !patch.dropped.length) return;
    try {
      await api(`/api/projects/${state.projectId}/overrides`,
                {method: "POST", body: {patch}});
      invalidateStages();
      hint.textContent = "고친 것을 저장했습니다 — 몸통(3번)을 다시 돌려야 반영됩니다";
      hint.className = "sfield-hint saved";
    } catch (e) {
      toast(String(e.message || e), "err");
    }
  }, 700);

  const bar = el("div", "obar");
  const n = doc.slides.length;
  const withSvg = doc.slides.filter((s) => s.has_svg).length;
  const withTab = doc.slides.filter((s) =>
    (s.blocks || []).some((b) => b.kind === "table")).length;
  const bad = doc.slides.filter((s) => (s.flags || []).length).length;
  bar.append(el("span", "ostat", `${n}장`),
             el("span", "ostat", `묶음 ${doc.groups.length}개`),
             el("span", "ostat", `그림 ${withSvg} · 표 ${withTab}`),
             el("span", "ostat" + (bad ? " warn" : ""), `어긋난 장 ${bad}`));
  const gotoDraft = el("button", "btn");
  gotoDraft.type = "button";
  gotoDraft.textContent = "원고 보기";
  gotoDraft.onclick = () => navigate("/draft");
  bar.appendChild(gotoDraft);
  page.appendChild(bar);

  const hint = el("div", "sfield-hint",
    "제목·말할 것·그림 종류를 고칠 수 있습니다. 고치면 3번(몸통)부터 다시 돌리세요.");
  page.appendChild(hint);

  let curGroup = null;
  const byGroup = Object.fromEntries(doc.groups.map((g) => [String(g.num), g.title]));

  for (const s of doc.slides) {
    const g = String(s.group || "");
    if (g && g !== curGroup) {
      curGroup = g;
      page.appendChild(el("h2", "ogroup", `${g}. ${byGroup[g] || ""}`));
    }

    const card = el("div", "ocard" + ((s.flags || []).length ? " bad" : ""));

    const hd = el("div", "ocard-hd");
    hd.append(el("span", "oid", s.data_id), el("span", "ono", s.no || ""));
    if (s.lines) hd.appendChild(el("span", "ostat", `${s.lines}줄`));
    if (s.height) hd.appendChild(el("span", "ostat", `${s.height}px`));
    if (s.has_svg) hd.appendChild(el("span", "otag svg", "그림"));
    if ((s.blocks || []).some((b) => b.kind === "table"))
      hd.appendChild(el("span", "otag tab", "표"));
    if (s.has_prompt) hd.appendChild(el("span", "otag img", "프롬프트"));
    for (const f of s.flags || [])
      hd.appendChild(el("span", "otag bad", FLAG_TXT[f] || f));
    card.appendChild(hd);

    const put = (k, v) => {
      patch.slides[s.data_id] = {...(patch.slides[s.data_id] || {}), [k]: v};
      save();
    };

    const title = el("input", "otitle");
    title.value = s.title || "";
    title.placeholder = "화면에 그대로 뜨는 한 줄";
    title.oninput = () => put("title", title.value.trim());
    card.appendChild(title);

    const say = el("textarea", "osay");
    say.rows = 2;
    say.value = s.say || "";
    say.placeholder = "이 화면을 띄우고 할 말 한두 문장 — 줄 등장 시각의 근거가 됩니다";
    say.oninput = () => put("say", say.value.trim());
    card.appendChild(say);

    const foot = el("div", "ocard-ft");
    for (const [v, label] of [["svg", "그림"], ["table", "표"]]) {
      const b = el("button", "sopt" + (s.visual === v ? " on" : ""));
      b.type = "button";
      b.textContent = label;
      b.onclick = () => {
        s.visual = v;
        put("visual", v);
        foot.querySelectorAll(".sopt").forEach((x) =>
          x.classList.toggle("on", x.textContent === label));
      };
      foot.appendChild(b);
    }
    const budget = el("input", "obudget");
    budget.type = "number";
    budget.min = "1";
    budget.max = "6";
    budget.value = String(s.blocks_budget || 4);
    budget.title = "줄 예산 — 그림·표 포함. 6을 넘길 수 없습니다";
    budget.oninput = () => put("blocks_budget",
      Math.max(1, Math.min(6, parseInt(budget.value || "4", 10) || 4)));
    foot.append(budget, el("span", "sfield-hint", "줄"));

    if ((s.pages || []).length)
      foot.appendChild(el("span", "sfield-hint",
        `${s.pages[0]}${s.pages[1] && s.pages[1] !== s.pages[0] ? "–" + s.pages[1] : ""}쪽`));

    const drop = el("button", "sopt drop");
    drop.type = "button";
    drop.textContent = "이 장 빼기";
    drop.onclick = () => {
      if (!patch.dropped.includes(s.data_id)) patch.dropped.push(s.data_id);
      card.classList.add("dropped");
      save();
    };
    foot.appendChild(drop);
    card.appendChild(foot);

    page.appendChild(card);
  }

  if (doc.dropped?.length) {
    const box = el("div", "card");
    box.appendChild(el("div", "card-title", "담지 못하고 버린 것"));
    const b = el("div", "card-body");
    b.appendChild(el("div", "sfield-hint",
      "장 예산을 올려 2번을 다시 돌리면 이것부터 들어갑니다."));
    doc.dropped.forEach((t) => b.appendChild(el("div", "rule-row", t)));
    box.appendChild(b);
    page.appendChild(box);
  }
}
