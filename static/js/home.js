/* 홈 — **무엇을 만드는 도구인지 한 판에 말한다.**
 *
 * 이 앱은 혼자 쓰이지 않는다. 낸 원고가 발표 쇼케이스(5178)로, 낸 JSON 이 이미지
 * 스튜디오로 간다. 그 사슬을 모르면 여기서 나온 파일을 어디에 넣어야 하는지
 * 알 수 없어서, 첫 화면이 그것부터 말한다.
 */
"use strict";

import { el, icon } from "./util.js";
import { navigate } from "./shell.js";

export const meta = {
  title: "작가 에이전트",
  subtitle: "단행본 한 장(章) PDF 를 넣으면 AI 아바타가 강의할 슬라이드 원고와 대본이 나옵니다",
};

const CHAIN = [
  ["단행본 PDF", "책에서 글을 뽑습니다. 머리글·쪽번호·여백 상자를 걷어냅니다"],
  ["이 앱", "장을 나누고 대본을 쓰고, 장마다 여섯 줄 안쪽으로 몸통과 그림을 만듭니다"],
  ["원고 HTML", "발표 쇼케이스(5178)의 「참고 자료」 칸에 넣으면 발표가 됩니다"],
  ["대본 TXT", "AI 아바타가 읽을 글. 이 글자 수의 총합이 그대로 영상 길이가 됩니다"],
];

export function mount(root) {
  const page = el("div", "spage");

  const lead = el("div", "card");
  lead.appendChild(el("div", "card-title", "무엇이 어디로 가나"));
  const body = el("div", "card-body");
  const list = el("div", "chain");
  CHAIN.forEach(([name, why], i) => {
    const row = el("div", "chain-row");
    row.append(el("i", "chain-n", String(i + 1)),
               el("span", "chain-name", name),
               el("span", "chain-why", why));
    list.appendChild(row);
  });
  body.appendChild(list);
  lead.appendChild(body);
  page.appendChild(lead);

  const rules = el("div", "card");
  rules.appendChild(el("div", "card-title", "원고가 지키는 것"));
  const rb = el("div", "card-body");
  [
    "h3 하나가 슬라이드 한 판입니다. 장 수를 여기서 정하면 발표 장 수가 정해집니다.",
    "한 판은 944 × 507 px 안에, 여섯 줄 이내입니다. 넘치면 내용을 줄이지 않고 장을 나눕니다.",
    "장마다 인라인 SVG 하나 또는 표 하나가 들어갑니다 — 줄글만 있는 화면을 만들지 않습니다.",
    "다 만든 뒤 진짜 브라우저에 띄워 장마다 높이를 잽니다. 어긋난 장은 이름으로 알려 줍니다.",
  ].forEach((t) => rb.appendChild(el("div", "rule-row", t)));
  rules.appendChild(rb);
  page.appendChild(rules);

  const foot = el("div", "sfoot");
  foot.appendChild(el("div", "sfoot-note",
    "책을 읽고 목차를 세우는 데 2~4분. 몸통과 그림까지 가면 10~20분 걸립니다."));
  const go = el("button", "btn primary lg");
  go.type = "button";
  go.append(icon("plus", 15), el("span", null, "새 원고 만들기"));
  go.onclick = () => navigate("/start");
  foot.appendChild(go);
  page.appendChild(foot);

  root.appendChild(page);
}
