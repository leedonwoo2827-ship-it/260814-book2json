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
  subtitle: "원고 HTML 은 발표 쇼케이스로, 프롬프트 JSON 은 이미지 스튜디오로",
};

/* 파일 이름 끝 → (무엇인가, 어디에 넣나). **긴 이름을 먼저** 본다 —
   「이미지프롬프트_부족분.json」이 「이미지프롬프트.json」에 먼저 걸리면 안 된다. */
const WHERE = [
  ["_원고.html", "원고 HTML",
   "발표 쇼케이스(localhost:5178)의 「새 발표」 → 참고 자료 칸에 끌어다 놓으세요. "
   + "h3 개수 + 1(표지) 만큼 장이 생깁니다."],
  ["이미지프롬프트_부족분.json", "부족분 프롬프트",
   "새로 생겼거나 몸통이 바뀐 장만 들어 있습니다. 이미 그린 그림을 지키려면 "
   + "전체 대신 이것을 넣으세요."],
  ["이미지프롬프트.json", "이미지 프롬프트 (전체)",
   "이미지 스튜디오의 📋 → 「슬라이드 JSON」 탭에 붙여 넣으세요. "
   + "크기는 1536 × 1024 로 잡힙니다."],
  ["이름바꾸기.txt", "이름 바꾸기 표",
   "번호가 밀린 그림 목록입니다. ★ 뒤에서부터 바꾸세요 — 앞에서부터 하면 "
   + "아직 안 바꾼 파일을 덮어씁니다."],
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
      const ok = await runSteps(["b6-assemble", "b7-check", "b8-export"], {
        btn: run, label,
        names: {"b6-assemble": "원고 조립", "b7-check": "실측 검증",
                "b8-export": "내보내기"},
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

    for (const f of doc.files) {
      const hit = WHERE.find(([suf]) => f.name.endsWith(suf));
      const card = el("div", "card");
      const t = el("div", "card-title");
      t.append(el("span", null, hit ? hit[1] : f.name),
               el("span", "ostat", `${f.kb}KB`));
      card.appendChild(t);
      const b = el("div", "card-body");
      b.appendChild(el("div", "rule-row", f.name));
      if (hit) b.appendChild(el("div", "sfield-hint", hit[2]));

      const row = el("div", "step-act");
      const dl = el("a", "btn");
      dl.href = `/api/projects/${state.projectId}/files/${encodeURIComponent(f.name)}`;
      dl.download = f.name;
      dl.textContent = "내려받기";
      row.appendChild(dl);

      const copy = el("button", "btn");
      copy.type = "button";
      copy.textContent = "경로 복사";
      copy.onclick = async () => {
        // 파일을 옮기는 것보다 **경로를 주는 쪽**이 맞다. 받는 앱들이 전부
        // 절대 경로를 입력칸으로 받는다.
        await navigator.clipboard.writeText(`${doc.dir}\\${f.name}`);
        toast("경로를 복사했습니다");
      };
      row.appendChild(copy);
      b.appendChild(row);
      card.appendChild(b);
      page.appendChild(card);
    }
  }

  await draw();
}
