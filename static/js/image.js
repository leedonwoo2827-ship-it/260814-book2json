/* 이미지 프롬프트 — **원장이 무엇을 그대로 쓰고 무엇을 새로 만들었나.**
 *
 * 이 화면이 답하는 질문은 하나다: *원고를 고쳤는데, 이미 만들어 둔 그림은 어떻게
 * 되나.* 답은 위쪽 띠에 숫자로 있다.
 *
 *     그대로   몸통이 안 바뀐 장. 프롬프트도 그림도 그대로 쓴다
 *     새로     새로 생기거나 몸통이 바뀐 장. 이 장만 다시 그리면 된다
 *     밀림     내용은 그대로인데 **번호가 밀린** 장. 그림 파일 이름만 바꾸면 된다
 *
 * ★ 번호(`n`)를 내보내기 전에도 보여 준다. 사람이 알고 싶은 것은 「이 장 그림이 몇
 *   번 파일인가」인데, 원장은 이름표로만 기억하기 때문이다.
 *
 * ★ 프롬프트를 손으로 고칠 수 있다. 고친 것은 원장에 바로 쓰이고, 4번을 다시
 *   돌려도 안 지워진다 — 몸통이 그대로면 「그대로 쓴다」 쪽으로 떨어진다.
 */
"use strict";

import { el, api, icon, toast, debounce } from "./util.js";
import { state, guard } from "./store.js";
import { navigate } from "./shell.js";

export const meta = {
  title: "이미지 프롬프트",
  subtitle: "가로형 그림 지시. 번호가 밀려도 이름표로 짝이 유지됩니다",
};

const TONE = {"그대로": "ok", "새로": "warn", "밀림": "warn"};

export async function mount(root) {
  if (!guard(root)) return;
  const page = el("div", "ipage");
  root.appendChild(page);
  page.appendChild(el("div", "side-empty", "읽는 중…"));

  let doc;
  try {
    doc = await api(`/api/projects/${state.projectId}/prompts`);
  } catch (e) {
    page.innerHTML = "";
    page.appendChild(el("div", "srun-line err", String(e.message || e)));
    return;
  }
  page.innerHTML = "";

  if (!doc.ready) {
    page.appendChild(el("div", "side-empty",
      "아직 목차가 없습니다. 현황판에서 2번부터 차례로 누르세요."));
    return;
  }

  const has = doc.slides.filter((s) => s.prompt);
  const cnt = (k) => doc.slides.filter((s) => s.state === k).length;

  const bar = el("div", "obar");
  bar.append(el("span", "ostat", `${doc.slides.length}장`),
             el("span", "ostat", `프롬프트 ${has.length}개`),
             el("span", "ostat ok", `그대로 ${cnt("그대로")}`),
             el("span", "ostat" + (cnt("새로") ? " warn" : ""), `새로 ${cnt("새로")}`),
             el("span", "ostat" + (cnt("밀림") ? " warn" : ""), `밀림 ${cnt("밀림")}`),
             el("span", "ostat", `비율 ${doc.aspect}`));
  const go = el("button", "btn");
  go.type = "button";
  go.textContent = "내보내기";
  go.onclick = () => navigate("/export");
  bar.appendChild(go);
  page.appendChild(bar);

  page.appendChild(el("div", "sfield-hint",
    "landscape 는 이미지 스튜디오에서 1536 × 1024 (3:2) 로 떨어집니다. "
    + "gpt-image 의 크기가 정사각 · 3:2 · 2:3 셋뿐이라 진짜 16:9 는 없습니다 — "
    + "가장 넓은 것이 이것이고, 영상에서 위아래가 잘려도 되게 좌우로 펼쳐 그리게 시켰습니다."));

  if (doc.renames?.length) {
    const box = el("div", "card warn");
    box.appendChild(el("div", "card-title",
      `번호가 밀린 장 ${doc.renames.length}개 — 이미 그린 그림이 있다면 이름을 바꾸세요`));
    const b = el("div", "card-body");
    b.appendChild(el("div", "sfield-hint",
      "★ 뒤에서부터 바꾸세요. 앞에서부터 하면 아직 안 바꾼 파일을 덮어씁니다. "
      + "내보내기를 누르면 이 목록이 「이름바꾸기.txt」 로도 나옵니다."));
    doc.renames.slice().sort((a, b2) => b2[1] - a[1]).forEach(([o, n, id]) =>
      b.appendChild(el("div", "rule-row",
        `${String(o).padStart(3, "0")}.png  →  ${String(n).padStart(3, "0")}.png    ${id}`)));
    box.appendChild(b);
    page.appendChild(box);
  }

  if (doc.retired?.length) {
    page.appendChild(el("div", "sfield-hint",
      `원고에서 빠진 장 ${doc.retired.length}개의 프롬프트는 원장에 남아 있습니다 — `
      + "그 장을 되살리면 그대로 돌아옵니다."));
  }

  for (const s of doc.slides) {
    const card = el("div", "icard");
    const hd = el("div", "icard-hd");
    hd.append(el("span", "inum", s.n ? String(s.n).padStart(3, "0") : "—"),
              el("span", "oid", s.data_id),
              el("span", "icard-t", s.title || ""));
    if (s.level) hd.appendChild(el("span", "otag", s.level));
    hd.appendChild(el("span", `pill ${TONE[s.state] || "idle"}`, s.state));
    if (s.state === "밀림") hd.appendChild(
      el("span", "sfield-hint", `${String(s.last_n).padStart(3, "0")}.png 였음`));
    card.appendChild(hd);

    if (!s.prompt) {
      card.appendChild(el("div", "srun-line",
        "프롬프트가 없습니다 — 현황판 4번을 누르세요"));
      page.appendChild(card);
      continue;
    }

    const ta = el("textarea", "iprompt");
    ta.rows = 4;
    ta.value = s.prompt;
    ta.spellcheck = false;
    const saved = el("span", "sfield-hint");
    ta.oninput = debounce(async () => {
      try {
        await api(`/api/projects/${state.projectId}/prompts/${encodeURIComponent(s.data_id)}`,
                  {method: "POST", body: {prompt: ta.value}});
        saved.textContent = "저장했습니다";
      } catch (e) {
        toast(String(e.message || e), "err");
      }
    }, 800);
    card.append(ta, saved);
    page.appendChild(card);
  }
}
