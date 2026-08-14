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
import { state, getStages, invalidateStages } from "./store.js";
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
  {n: 2, name: "장 나누기", keys: ["b2-outline"],
   why: "h3 하나가 슬라이드 한 판 — 여기서 장 수가 정해집니다", paid: true,
   go: "/outline", goLabel: "목차 보기"},
  {n: 3, name: "몸통 쓰기", keys: ["b3-write", "b4-figure"],
   why: "장마다 여섯 줄 안쪽으로. 장마다 그림 하나씩", paid: true,
   go: "/draft", goLabel: "원고 보기"},
  {n: 4, name: "이미지 프롬프트", keys: ["b5-imgprompt"],
   why: "가로형 그림 지시. 안 바뀐 장은 원장에서 그대로 씁니다", paid: true,
   go: "/image", goLabel: "프롬프트 보기"},
  {n: 5, name: "조립하고 재기", keys: ["b6-assemble", "b7-check"],
   why: "원고 한 파일로 묶고 944×507 을 진짜로 잽니다", paid: false,
   go: "/draft", goLabel: "실측 보기"},
  {n: 6, name: "내보내기", keys: ["b8-export"],
   why: "원고 HTML · 프롬프트 JSON · 부족분 · 이름바꾸기", paid: false,
   go: "/export", goLabel: "파일 보기"},
];

const STATE_TXT = {
  missing: ["아직", "idle"],
  stale: ["다시 해야 함", "warn"],
  fresh: ["됨", "ok"],
  degraded: ["됐지만 경고", "warn"],
  skipped: ["건너뜀", "idle"],
};

export async function mount(root) {
  const page = el("div", "bpage");
  const list = el("div", "steps");
  page.appendChild(list);
  root.appendChild(page);

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

    let blocked = false;                 // 앞이 안 끝나면 뒤는 잠근다
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

      if (!done) blocked = true;         // 이 줄이 안 끝났으면 아래는 잠긴다
    }

    const foot = el("div", "sfoot");
    foot.appendChild(el("div", "sfoot-note",
      `지금까지 쓴 값 $${(data.cost_usd || 0).toFixed(2)}`));
    list.appendChild(foot);
  }

  await draw();
}
