/* 내보내기 — **어느 파일을 어디에 넣는지까지 말한다.**
 *
 * 파일 목록만 두면 반드시 다시 묻게 된다: "이 JSON 을 어디 넣으라고요?" 이 앱은
 * 사슬의 가운데 토막이라, 나가는 파일마다 **받는 쪽**을 같이 적는다.
 */
"use strict";

import { el, api, icon, toast } from "./util.js";
import { state, guard } from "./store.js";
import { runSteps } from "./runner.js";
import { navigate } from "./shell.js";

export const meta = {
  title: "내보내기",
  subtitle: "원고 HTML 과 대본을 발표 쇼케이스로 넘깁니다",
};

/* 파일 이름 끝 → (무엇인가, 어디에 넣나). **긴 이름을 먼저** 본다 —
   「이미지프롬프트_부족분.json」이 「이미지프롬프트.json」에 먼저 걸리면 안 된다. */
const WHERE = [
  ["_원고.html", "원고 HTML",
   "발표 쇼케이스(localhost:5178)의 「새 발표」 → 참고 자료 칸에 끌어다 놓으세요. "
   + "h3 개수 + 1(표지) 만큼 장이 생깁니다."],
  // 이 칸은 그냥 글자로 뜬다 — 마크다운이 아니다. 별표를 쓰면 별표가 보인다.
  ["_대본.txt", "대본",
   "AI 아바타가 읽을 글입니다. 이 글자 수의 총합이 곧 영상 길이입니다(420자 = 1분). "
   + "원고 안의 data-say 와 같은 글이라, 고칠 때는 목차 화면에서 고치고 "
   + "4번(마무리)을 다시 돌리세요."],
  // ★ 이미지 프롬프트 세 파일(전체·부족분·이름바꾸기)이 여기 있었다. 2026-08-14 에
  //   뺐다 — 그림 지시는 다른 에이전트가 만든다. 지난번에 만든 파일이 폴더에
  //   남아 있으면 아래 목록에 이름 그대로 뜨는데, 그건 **옛것**이다.
  ["실측.json", "실측 결과",
   "장마다 잰 높이와 줄 수입니다. 어긋난 장을 되짚을 때만 보면 됩니다."],
];

export async function mount(root) {
  if (!guard(root)) return;
  const page = el("div", "spage");
  root.appendChild(page);

  async function draw() {
    page.innerHTML = "";
    let doc;
    try {
      doc = await api(`/api/projects/${state.projectId}/files`);
    } catch (e) {
      page.appendChild(el("div", "srun-line err", String(e.message || e)));
      return;
    }

    const bar = el("div", "obar");
    bar.appendChild(el("span", "ostat", doc.dir));
    const run = el("button", "btn primary");
    const label = el("span", "step-run-label");
    run.type = "button";
    run.textContent = doc.files.length ? "다시 내보내기" : "내보내기";
    run.onclick = async () => {
      const ok = await runSteps(["b6-assemble", "b7-check"], {
        btn: run, label,
        names: {"b6-assemble": "원고 조립", "b7-check": "실측 검증"},
        onLog: (lines) => lines.forEach((t) =>
          logs.appendChild(el("div", "srun-line", t))),
      });
      if (ok) toast("내보냈습니다");
      draw();
    };
    bar.append(run, label);
    page.appendChild(bar);

    const logs = el("div", "srun");
    page.appendChild(logs);

    if (!doc.files.length) {
      page.appendChild(el("div", "side-empty",
        "아직 내보낸 것이 없습니다. 위 단추를 누르면 조립 → 실측 → 내보내기가 차례로 돕니다."));
      return;
    }

    const card = (f, inBak) => {
      const hit = WHERE.find(([suf]) => f.name.endsWith(suf));
      const box = el("div", "card" + (inBak ? " muted" : ""));
      const t = el("div", "card-title");
      t.append(el("span", null, hit ? hit[1] : f.name),
               el("span", "ostat", `${f.kb}KB`));
      box.appendChild(t);
      const b = el("div", "card-body");
      b.appendChild(el("div", "rule-row", f.name));
      if (hit) b.appendChild(el("div", "sfield-hint", hit[2]));

      const row = el("div", "step-act");
      const q = inBak ? "?bak=1" : "";
      const dl = el("a", "btn");
      dl.href = `/api/projects/${state.projectId}/files/${encodeURIComponent(f.name)}${q}`;
      dl.download = f.name;
      dl.textContent = "내려받기";
      row.appendChild(dl);

      const copy = el("button", "btn");
      copy.type = "button";
      copy.textContent = "경로 복사";
      copy.onclick = async () => {
        // 파일을 옮기는 것보다 **경로를 주는 쪽**이 맞다. 받는 앱들이 전부
        // 절대 경로를 입력칸으로 받는다.
        await navigator.clipboard.writeText(
          `${doc.dir}${inBak ? "\bak" : ""}\${f.name}`);
        toast("경로를 복사했습니다");
      };
      row.appendChild(copy);
      b.appendChild(row);
      box.appendChild(b);
      return box;
    };

    // 위 칸 = **넘길 것.** 지금은 원고 HTML 하나다.
    for (const f of doc.files) page.appendChild(card(f, false));

    // 아래 칸 = 안 넘기는 것. 버리지도 않는다 — 되짚을 때 여기서 찾는다.
    if ((doc.bak || []).length) {
      page.appendChild(el("h2", "ogroup", "bak — 넘기지 않는 것"));
      page.appendChild(el("div", "sfield-hint",
        "폴더 안 bak\ 에 있습니다. 대본은 아바타가 읽을 글을 사람이 통독하는 자리이고, "
        + "실측은 어긋난 장을 되짚을 때만 봅니다."));
      for (const f of doc.bak) page.appendChild(card(f, true));
    }
  }

  await draw();
}
