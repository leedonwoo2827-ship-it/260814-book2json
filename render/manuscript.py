# -*- coding: utf-8 -*-
"""원고 HTML 조립 — **규약을 어길 수 없게 만드는 자리.**

계약서는 `260812-summary-shocase/_new-context/5-이론화-에이전트에게.md` 다.
그 편지는 사람에게 "이렇게 써 주세요" 라고 부탁한 것인데, 여기서는 부탁이 아니라
**구조로 못 박는다.** 조립기가 낼 수 있는 모양이 하나뿐이면 어길 방법이 없다.

    <body> 바로 밑이 평평하다        감싸는 <div> 를 아예 안 만든다
    h1 표지 · h2 묶음 · h3 장 하나   층을 세 개만 만든다
    li 하나에 한 생각                blocks 배열이 그대로 줄이 된다
    바깥 파일 참조 없음              <style> 은 이 파일 안의 상수 하나뿐
    position:fixed 없음              같은 이유
    script 없음                      기계용 블록 하나만, 그것도 실행되지 않는 JSON

★ `<style>` 은 `260812-summary-shocase/_context/_newcontext/1summary_planning.html`
  에서 그대로 가져왔다. **고치지 마라.** 저쪽 파이프라인이 이 CSS 를 `.doc` 밑으로
  가둔 뒤 944px 폭에서 배치하고 1.627배로 확대한다. 여기 숫자 하나가 바뀌면
  줄바꿈 위치가 달라져서 장 높이가 통째로 달라진다.

★ `.q` 배지는 원래 「모의 N회 M번」 같은 문번을 접어 두는 칸이었다. 단행본에는
  문번이 없어서 **원서 쪽수**로 돌려 쓴다. 사람이 원문과 대조하는 데 쓰고, 발표
  쇼케이스는 제목에서 자동으로 떼어 내므로 화면에는 안 뜬다.
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional

# ── 원고 스타일 ────────────────────────────────────────────────────────────
# 손대지 말 것. 위 주석의 이유가 전부다.
DOC_CSS = """
body { font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
       line-height: 1.7; color: #1c2530; padding: 8px 4px 40px; }
h1 { font-size: 1.6rem; margin: 0 0 18px; padding-bottom: 10px;
     border-bottom: 3px solid #2f6b66; color: #1f4a46; }
h2 { font-size: 1.22rem; margin: 2.2em 0 0.6em; padding-left: 10px;
     padding-bottom: 0.3em; border-left: 5px solid #2f6b66;
     border-bottom: 2px solid currentColor; color: #1f4a46; line-height: 1.5; }
h3 { font-size: 1.04rem; margin: 1.5em 0 0.4em; color: #2f6b66; line-height: 1.55; }
h2 .q, h3 .q { display: inline-block; font-weight: 400; font-size: 0.72em;
               line-height: 1.5; vertical-align: middle; white-space: normal; }
p { line-height: 1.75; margin: 0.4em 0; }
ul, ol { margin: 0.4em 0 0.8em; padding-left: 1.3em; }
li { margin: 0.28em 0; line-height: 1.7; }
b { font-weight: 600; }
code { background: #f2f5f7; padding: 1px 5px; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; margin: 0.7em 0 1em;
        font-size: 0.95em; table-layout: fixed; }
th, td { border: 1px solid rgba(127, 169, 208, 0.55); padding: 0.42em 0.6em;
         text-align: left; vertical-align: top; line-height: 1.6; }
th { background: rgba(157, 195, 230, 0.28); font-weight: 600; }
figure { margin: 10px 0; text-align: center; }

/* ★ 근거 쪽 — **접어 둔다.** 눌러야 쪽 범위가 보인다.
   JS 를 쓰지 않는다: 이 원고를 받는 쪽(발표 쇼케이스)이 <script> 를 전부 제거하고
   innerHTML 로 넣기 때문에, JS 로 만들면 안 접힌다. label + checkbox 로 CSS 만
   써서 만든다. <label>·<input>·<b>·<span> 은 전부 phrasing 이라 <h3> 안에 넣어도 된다. */
.q { display: inline; margin-left: 6px; cursor: pointer; user-select: none;
     font-size: .84em; font-weight: 600; color: #2f6b66;
     background: #eaf3f2; border: 1px solid #bcdad6; border-radius: 999px;
     padding: 1px 7px; white-space: nowrap; vertical-align: middle; }
.q:hover { background: #d9ecea; }
.q > input { position: absolute; opacity: 0; width: 0; height: 0; }
.q > b::before { content: "\\25B8"; margin-right: 3px; font-weight: 400; }
.q > input:checked ~ b::before { content: "\\25BE"; }
.q > .qn { display: none; }
.q > input:checked ~ .qn { display: inline; margin-left: 6px; font-weight: 400;
                           color: #46605c; white-space: normal; }

/* ★ 그림 높이 상한. **폭만 막으면 안 된다** — 인라인 SVG 는 viewBox 비율대로 폭에
   맞춰 늘어나므로, 가로로 넓은 도식이 화면 절반을 먹는다. `width:auto` +
   `max-height` 로 비율을 지키면서 높이로 자른다. */
svg, img { max-height: 240px; width: auto; max-width: 100%; height: auto;
           display: block; margin: 10px auto; }

/* ★ 어떤 경우에도 가로로 밀지 않는다. 이 원고는 화면이 되므로 마지막 방어선이다. */
* { max-width: 100%; }
body { overflow-x: hidden; overflow-wrap: anywhere; }
""".strip()


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def page_badge(pages: List[int]) -> str:
    """`.q` 배지 — 접힌 채로는 첫 쪽만, 펴면 범위가 보인다."""
    if not pages:
        return ""
    lo = pages[0]
    hi = pages[-1] if len(pages) > 1 else lo
    span = f"원서 {lo}쪽" if lo == hi else f"원서 {lo}–{hi}쪽"
    return (f'<label class="q"><input type="checkbox"><b>{lo}</b>'
            f'<span class="qn">{esc(span)}</span></label>')


def _body(blocks: List[Dict[str, Any]], svg: Optional[str]) -> List[str]:
    """장 하나의 몸통. **`<li>` 는 이어진 것끼리 한 `<ul>` 로 묶는다.**

    묶는 이유: 규약은 `<li>` 하나를 한 줄로 세지만, HTML 에서 `<li>` 는 `<ul>` 밖에
    혼자 설 수 없다. 낱개마다 `<ul>` 을 씌우면 목록 사이 여백(0.4em + 0.8em)이
    줄마다 붙어 장 높이가 실제보다 30~40px 커진다 — 그 차이로 507px 을 넘긴다.
    """
    out: List[str] = []
    bucket: List[str] = []

    def flush() -> None:
        if bucket:
            out.append("<ul>\n" + "\n".join(f"  <li>{x}</li>" for x in bucket) + "\n</ul>")
            bucket.clear()

    for b in blocks or []:
        kind, h = b.get("kind"), (b.get("html") or "").strip()
        if not h:
            continue
        if kind == "li":
            bucket.append(h)
            continue
        flush()
        out.append(h if kind == "table" else f"<p>{h}</p>")
    flush()
    if svg:
        out.append(svg)
    return out


def build(*, title: str, book: str, groups: List[Dict[str, Any]],
          slides: List[Dict[str, Any]], figures: Dict[str, str],
          prompts: Dict[str, Dict[str, Any]]) -> str:
    """원고 한 파일. `slides` 는 **화면에 나갈 순서 그대로** 온다.

    각 `slide` 는 `{data_id, group, no, title, say, pages, blocks}` 다.
    """
    parts: List[str] = [
        "<!DOCTYPE html>", '<html lang="ko">', "<head>",
        '<meta charset="utf-8">',
        f"<title>{esc(title)}</title>",
        "<style>", DOC_CSS, "</style>",
        "</head>", "<body>",
        f"<h1>{esc(title)}</h1>",
    ]
    if book:
        parts.append(f"<p>{esc(book)}</p>")

    by_group: Dict[str, str] = {str(g.get("num")): (g.get("title") or "") for g in groups}
    seen_group: Optional[str] = None

    for s in slides:
        g = str(s.get("group") or "")
        if g and g != seen_group:
            seen_group = g
            parts.append(f"<h2>{esc(g + '. ' + by_group.get(g, ''))}</h2>")

        did = s["data_id"]
        head = [f'<h3 data-id="{esc(did)}"']
        if say := (s.get("say") or "").strip():
            head.append(f'    data-say="{esc(say)}"')
        # ★ 그림 지시문을 제목에 심는다. 원고와 그림이 **한 파일 안에서** 짝지어져
        #   있어야, 원고를 고친 사람이 그림도 같이 봐야 한다는 것을 잊지 않는다.
        if img := ((prompts.get(did) or {}).get("prompt") or "").strip():
            head.append(f'    data-img="{esc(img)}"')
        label = ((s.get("no") or "") + " " + (s.get("title") or "")).strip()
        parts.append("\n".join(head) + ">" + esc(label) + page_badge(s.get("pages") or [])
                     + "</h3>")
        parts.extend(_body(s.get("blocks") or [], figures.get(did)))

    # ★ 기계가 읽을 블록. 속성(`data-img`)과 겹치지만 **속성은 사람이 읽고 이것은
    #   기계가 읽는다.** 발표 쇼케이스의 `core/htmldoc.py` 가 `#manifest` 를 꺼내
    #   쓰는 것과 같은 수법이다. `<script>` 는 저쪽이 어차피 제거하므로 원고를
    #   오염시키지 않고, 브라우저에서도 실행되지 않는다(type 이 JSON 이다).
    #   `</script>` 가 값 안에 섞여 태그가 일찍 닫히는 것만 막는다.
    payload = json.dumps({"by_id": prompts}, ensure_ascii=False)
    parts += ['<script type="application/json" id="imgprompts">',
              payload.replace("<", "\\u003c"), "</script>",
              "</body>", "</html>"]
    return "\n".join(parts) + "\n"
