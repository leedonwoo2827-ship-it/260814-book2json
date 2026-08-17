/* 현황판 — **무엇이 남았나. 다음 숫자를 누르면 된다.**
 *
 * 발표 쇼케이스의 현황판은 씬 × 4열 매트릭스다. 거기서는 확정할 것이 장마다
 * 넷이라 그 모양이 맞았다. 여기는 다르다 — 확정할 것은 장마다가 아니라 **단계마다**
 * 하나고, 단계가 여섯 개뿐이다. 그래서 여섯 줄짜리 사다리로 둔다.
 *
 * ★ 순서가 곧 규칙이다. 앞이 안 끝났으면 뒤는 눌리지 않는다. 목차를 확정하기 전에
 *   몸통을 쓰면 예순 장을 다시 써야 한다 — 그게 이 앱에서 제일 비싼 실수다.
 *
 * ★ **돈이 드는 단계와 안 드는 단계를 눈으로 갈라 놓는다.** 다시 눌러도 되는 것과
 *   누를 때마다 값을 치르는 것이 같은 모양이면, 사람이 조심하느라 아무것도 못 누른다.
 */
"use strict";

import { $, el, api, icon, toast } from "./util.js";
import { state, getStages, invalidateStages, guard } from "./store.js";
import { navigate } from "./shell.js";
import { runSteps } from "./runner.js";

export const meta = {
  title: "현황판",
  subtitle: "무엇이 남았나. 위에서부터 차례로 누르면 됩니다",
};

/* 사람이 누르는 순서. **`core/steps.py` 의 STEPS 와 같은 값이어야 한다.** */
const STEPS = [
  {n: 1, name: "책에서 글 뽑기", keys: ["b1-pdf"],
   why: "PDF 를 쪽별로 읽어 머리글·쪽번호를 걷어냅니다", paid: false},
  {n: 2, name: "장 나누기와 대본", keys: ["b2-outline"],
   why: "h3 하나가 슬라이드 한 판 — 여기서 장 수와 영상 길이가 정해집니다", paid: true,
   go: "/outline", goLabel: "목차 보기"},
  {n: 3, name: "몸통 쓰기", keys: ["b3-write", "b4-figure"],
   why: "장마다 여섯 줄 안쪽으로. 장마다 그림 하나씩", paid: true,
   go: "/draft", goLabel: "원고 보기"},
  // ★ 넷째 줄이 마지막이다. 「이미지 프롬프트」와 「내보내기」가 빠졌다 —
  //   그림 지시는 다른 에이전트가 만들고(2026-08-14), 남은 산출물은 조립·실측이
  //   그 자리에서 파일로 쓴다. 몸통을 쓰고 나면 남는 것은 돈 안 드는 한 줄뿐이다.
  {n: 4, name: "마무리 — 조립하고 재기", keys: ["b6-assemble", "b7-check"],
   why: "원고·대본을 파일로 쓰고 944×507 을 진짜로 잽니다", paid: false,
   go: "/export", goLabel: "파일 보기"},
];

const STATE_TXT = {
  missing: ["아직", "idle"],
  stale: ["다시 해야 함", "warn"],
  fresh: ["됨", "ok"],
  degraded: ["됐지만 경고", "warn"],
  skipped: ["건너뜀", "idle"],
};

/* ── 목표 길이 ──────────────────────────────────────────────────────────────
 *
 * 사다리 맨 위에 둔다. **이 원고가 몇 분짜리를 노리는지**가 2번(장 나누기)의
 * 입력이라, 누르기 전에 보여야 한다. 다 만들고 나서 5분 30초인 것을 알면 그때는
 * 목차부터 다시 돌려야 한다(2026-08-14).
 *
 * 이미 만든 원고도 여기서 길이를 바꿀 수 있다 — 바꾸면 2번이 낡은 것으로 잡힌다.
 */
async function lengthCard(box) {
  let d;
  try {
    d = await api(`/api/projects/${state.projectId}/length`);
  } catch { return; }

  box.innerHTML = "";
  const row = el("div", "step lenhead");
  const hd = el("div", "step-hd");
  hd.append(el("span", "step-name", "이 원고의 길이"));
  const now = d.now;
  if (now) {
    hd.appendChild(el("span", `pill ${now.short ? "warn" : "ok"}`,
      `지금 ${now.clock}`));
  }
  row.appendChild(hd);

  const chips = el("div", "step-act");
  for (const o of d.options || []) {
    const on = o.minutes === d.target_min;
    const b = el("button", "btn" + (on ? " primary" : ""));
    b.type = "button";
    b.textContent = `${o.minutes}분`;
    b.onclick = async () => {
      b.disabled = true;
      try {
        await api(`/api/projects/${state.projectId}/length`,
                  {method: "POST", body: {target_min: o.minutes}});
        invalidateStages();
        toast(`목표를 ${o.minutes}분으로 바꿨습니다 — 2번부터 다시 돌리세요`);
      } catch (e) {
        toast(String(e.message || e), "err");
      }
      await lengthCard(box);
      refresh();                       // 사다리도 다시 그린다 — 2번이 낡았을 것이다
    };
    chips.appendChild(b);
  }
  row.appendChild(chips);

  const p = d.plan || {};
  row.appendChild(el("div", "step-why",
    `원문 ${(d.source_chars || 0).toLocaleString()}자 · 목표 ${p.minutes}분이면 `
    + `대본 ${(p.say_total || 0).toLocaleString()}자 · ${p.slides}장 · 장당 `
    + `${p.say_per_slide}자(${p.seconds_per_slide}초)입니다`));
  if (now) {
    row.appendChild(el("div", now.short ? "step-warn" : "step-why",
      now.short ? `${now.note} — 목차 화면에서 말을 채우거나 2번부터 다시 돌리세요`
                : `지금 대본 ${now.say_chars.toLocaleString()}자 · 목표의 ${now.pct}%`));
  }
  for (const w of (p.warnings || []).slice(0, 2))
    row.appendChild(el("div", "step-warn", w));

  box.appendChild(row);
}

/* 길이 카드가 사다리를 다시 그리게 하는 손잡이. 카드는 mount 밖에 있어서
   안쪽 `draw` 를 직접 못 부른다. */
let refresh = () => {};

export async function mount(root) {
  if (!guard(root)) return;
  const page = el("div", "bpage");
  const lenBox = el("div", "steps");
  const list = el("div", "steps");
  page.append(lenBox, list);
  root.appendChild(page);
  lengthCard(lenBox);

  async function draw() {
    let data;
    try {
      data = await getStages(true);
    } catch (e) {
      list.innerHTML = "";
      list.appendChild(el("div", "srun-line err", String(e.message || e)));
      return;
    }
    const by = Object.fromEntries((data.stages || []).map((s) => [s.key, s]));
    list.innerHTML = "";

    let blocked = false;                 // 앞 단계의 결과가 아예 없으면 잠근다
    for (const st of STEPS) {
      const mine = st.keys.map((k) => by[k]).filter(Boolean);
      if (!mine.length) continue;

      // 여러 단계를 묶은 줄은 **제일 나쁜 상태**를 말한다. 하나가 안 됐는데
      // "됨" 이라고 쓰면 사람이 다음으로 넘어간 뒤에야 안다.
      const rank = {missing: 0, stale: 1, degraded: 2, skipped: 3, fresh: 4};
      const worst = mine.reduce((a, b) => (rank[a.state] <= rank[b.state] ? a : b));
      const [txt, tone] = STATE_TXT[worst.state] || ["?", "idle"];
      const cost = mine.reduce((a, s) => a + (s.cost_usd || 0), 0);
      const warns = mine.flatMap((s) => s.warnings || []);
      const done = worst.state === "fresh" || worst.state === "skipped"
                   || worst.state === "degraded";
      // ★ **잠그는 근거는 「낡음」이 아니라 「없음」이다.**
      //   앞 단계가 낡았다고 뒤를 잠그면, 프롬프트 한 줄만 고쳐도 이미 잘 나온
      //   원고를 못 내보낸다(2026-08-14: 대본 지침을 고쳤더니 19장 목차가 통째로
      //   낡음이 되고 마무리가 잠겼다). 낡음은 **다시 할지 사람이 정하는 것**이고,
      //   앞 단계의 결과가 아예 없을 때만 뒤가 성립하지 않는다.
      //
      // ★ **한 줄 안에서 서로를 기다리는 것은 잠글 이유가 아니다.** 3번 줄은
      //   몸통(b3)과 그림(b4) 두 단계인데, 그림은 몸통이 끝나기 전까지 늘 「막힘」
      //   이다 — 누르면 차례로 도니까 그게 맞다. 그것까지 세는 바람에 3번이 영영
      //   안 눌렸다. 그래서 **이 줄 밖의** 단계가 비었을 때만 잠근다.
      const own = new Set(st.keys);
      blocked = mine.some((s) =>
        (s.missing_deps || []).some((d) => !own.has(d)));

      const row = el("div", "step" + (blocked ? " locked" : "") + (done ? " done" : ""));
      const head = el("div", "step-hd");
      head.append(el("i", "step-n", String(st.n)),
                  el("span", "step-name", st.name),
                  el("span", `pill ${tone}`, txt));
      if (st.paid) head.appendChild(el("span", "step-paid", "돈 듦"));
      if (cost) head.appendChild(el("span", "step-cost", `$${cost.toFixed(2)}`));
      row.appendChild(head);
      row.appendChild(el("div", "step-why", st.why));

      for (const w of warns.slice(0, 3)) row.appendChild(el("div", "step-warn", w));

      const act = el("div", "step-act");
      const label = el("span", "step-run-label");
      const run = el("button", "btn" + (blocked ? "" : " primary"));
      run.type = "button";
      run.disabled = blocked;
      run.textContent = done ? "다시" : "실행";
      run.onclick = async () => {
        const ok = await runSteps(st.keys, {
          btn: run, label,
          names: Object.fromEntries(st.keys.map((k) => [k, by[k].label])),
          onLog: (lines) => lines.forEach((t) =>
            act.insertBefore(el("div", "srun-line", t), label)),
        });
        invalidateStages();
        if (ok) toast(`${st.n}. ${st.name} 끝`);
        draw();
      };
      act.append(run, label);

      if (st.go) {
        const go = el("button", "btn");
        go.type = "button";
        go.disabled = !done;
        go.textContent = st.goLabel;
        go.onclick = () => navigate(st.go);
        act.appendChild(go);
      }
      row.appendChild(act);
      list.appendChild(row);

    }

    const foot = el("div", "sfoot");
    foot.appendChild(el("div", "sfoot-note",
      `지금까지 쓴 값 $${(data.cost_usd || 0).toFixed(2)}`));
    list.appendChild(foot);
  }

  refresh = draw;
  await draw();
}
