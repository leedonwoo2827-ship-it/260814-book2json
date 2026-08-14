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
  over: "한 화면을 넘침", longer: "줄이 많음", empty: "몸통 없음",
};

/* 공백을 뺀 글자 수. **core/narration.py 의 `count()` 와 같은 셈법이어야 한다** —
   화면에서 센 글자와 서버가 센 글자가 다르면 「목표의 몇 %」가 두 값이 된다. */
const say_len = (s) => (s || "").replace(/\s+/g, "").length;

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

  // 목표 길이 — 장마다 말이 몇 자여야 하는지의 근거. 못 받아 와도 목차는 보여야 한다.
  let len = null;
  try {
    len = await api(`/api/projects/${state.projectId}/length`);
  } catch { /* 길이 칸만 안 뜬다 */ }
  const perSlide = len?.plan?.say_per_slide || 0;
  const cpm = len?.plan?.chars_per_min || 420;

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

  /* ★ 대본 총량 = 영상 길이. 목차 화면에서 이걸 안 보여 주면, 짧다는 사실을
     영상이 나온 뒤에 안다(2026-08-14: 19장이 5분 30초). 장마다 말을 고칠 때마다
     여기 숫자가 따라 움직인다 — 채우면 채우는 만큼 길어지는 것이 보여야 한다. */
  const clock = (c) => {
    const t = Math.round(c / cpm * 60);
    return `${Math.floor(t / 60)}분 ${String(t % 60).padStart(2, "0")}초`;
  };
  const totalStat = el("span", "ostat");
  bar.appendChild(totalStat);
  const retotal = () => {
    const got = doc.slides.reduce((a, s) => a + say_len(s.say), 0);
    const want = len?.plan?.say_total || 0;
    const short = want && got < want * 0.85;
    totalStat.className = "ostat" + (short ? " warn" : (want ? " ok" : ""));
    totalStat.textContent = `대본 ${got.toLocaleString()}자 → ${clock(got)}`
      + (want ? ` (목표 ${len.plan.minutes}분)` : "");
  };
  const gotoDraft = el("button", "btn");
  gotoDraft.type = "button";
  gotoDraft.textContent = "원고 보기";
  gotoDraft.onclick = () => navigate("/draft");
  bar.appendChild(gotoDraft);
  page.appendChild(bar);

  const hint = el("div", "sfield-hint",
    "제목·말할 것·그림 종류를 고칠 수 있습니다. 고치면 3번(몸통)부터 다시 돌리세요."
    + (perSlide ? ` 말은 장당 ${perSlide}자가 목표입니다 — 그 총합이 영상 길이입니다.`
                : ""));
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
    // 「프롬프트」 칩이 여기 있었다 — 그림 지시가 붙었는지 표시하던 것인데,
    // 그 단계가 이 앱에서 빠졌다(2026-08-14).
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

    // 말 — **이 글이 그대로 내레이션이 된다.** 글자 수를 옆에 붙여 둔다.
    const sayStat = el("span", "ostat");
    hd.appendChild(sayStat);
    const say = el("textarea", "osay");
    say.rows = 4;
    say.value = s.say || "";
    say.placeholder = perSlide
      ? `이 화면을 띄우고 할 말 ${perSlide}자 안팎 — 이 글이 그대로 내레이션이 됩니다`
      : "이 화면을 띄우고 할 말 — 이 글이 그대로 내레이션이 됩니다";
    const restat = () => {
      const c = say_len(say.value);
      const thin = perSlide && c < perSlide * 0.6;
      sayStat.className = "ostat" + (thin ? " warn" : "");
      sayStat.textContent = `말 ${c}자 · ${Math.round(c / cpm * 60)}초`
        + (perSlide ? ` / ${perSlide}자` : "");
    };
    say.oninput = () => {
      s.say = say.value;
      restat();
      retotal();
      put("say", say.value.trim());
    };
    restat();
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
  retotal();

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
