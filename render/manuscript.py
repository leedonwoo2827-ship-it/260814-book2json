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
  문번이 없어서 **책 쪽수**로 돌려 쓴다. 사람이 원문과 대조하는 데 쓰고, 발표
  쇼케이스는 제목에서 자동으로 떼어 내므로 화면에는 안 뜬다.
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional

# ── 원고 스타일 ────────────────────────────────────────────────────────────
#
# 뼈대는 `260812-summary-shocase/_context/_newcontext/1summary_planning.html` 의
# 것을 그대로 쓰고, 결만 `_assetes/DESIGN.md`(KOICA·UBION 템플릿)에 맞췄다.
#
# ★ **그린 → 파랑 1:1 치환.** 가이드는 그린이 주조색인데, 이 원고의 그림(SVG)이
#   이미 파랑 계열을 쓰고 있어서 색을 두 갈래로 두면 한 화면 안에서 결이 갈린다.
#   대응은 그대로다:
#       Primary Green #2A9760  →  Primary Blue #2E75B6
#       Deep Green    #1F9155  →  Deep Blue    #1F4E79
#       Tint 1        #93D0B2  →  #9DC3E6
#       Tint 2        #E3F5EA  →  #DEEBF7
#   슬레이트 뉴트럴(#334155 · #94A3B8 · #CBD5E1 · #E2E8F0 · #F1F5F9)은 가이드
#   그대로다. 포인트 블루(#0079FF)는 로고 전용이라 안 쓴다.
#
# ★ **여기 스타일은 「몸통」에만 닿는다.** 발표 쇼케이스는 제목을 자기 CSS(`.hs-t`,
#   34px)로 다시 그리고 `.doc` 안쪽만 오려 간다. 그래서 h1·h2·h3 를 아무리 꾸며도
#   영상에는 안 나온다 — 사람이 원고 파일을 열어 볼 때만 보인다. 반대로 p·li·
#   table·svg 는 **그대로 영상이 된다.** 공들일 자리가 거기다.
#
# ★ **글자 크기를 키우지 않았다.** 한 장이 944 × 507px 안에 들어가야 하는데,
#   16px 본문에서 4~6줄로 재어 둔 값이다. 크기를 올리면 그 예산이 무너져 장마다
#   축소가 걸린다. 바꾼 것은 색·굵기·여백·구분선이지 크기가 아니다.
#
# ★ 폰트는 **바깥에서 안 받아온다.** 가이드가 Noto Sans KR 을 쓰지만 `@import` 는
#   규약 금지고, 완성본은 파일 한 장으로 나가 바깥 것이 안 따라간다. 설치돼 있으면
#   쓰고 없으면 조용히 맑은 고딕으로 내려앉는 순서로만 적는다.
DOC_CSS = """
body { font-family: "Noto Sans KR", "Pretendard", "Malgun Gothic", "맑은 고딕",
                    system-ui, sans-serif;
       font-size: 16px; line-height: 1.75; color: #334155;
       letter-spacing: -0.005em; padding: 8px 4px 40px; }

/* 제목 — 원고 파일을 사람이 열어 볼 때만 보인다(영상에는 쇼케이스 제목이 뜬다).
   가이드의 「2색 제목」을 따라 기본은 슬레이트, 강조는 파랑으로 둔다. */
h1 { font-size: 1.75rem; font-weight: 700; letter-spacing: -0.03em;
     margin: 0 0 6px; color: #334155; }
h1 + p { margin: 0 0 22px; padding-bottom: 14px; color: #94A3B8;
         font-size: 0.9rem; border-bottom: 1px solid #E2E8F0; }
h2 { font-size: 1.05rem; font-weight: 700; letter-spacing: -0.02em;
     margin: 2.4em 0 0.8em; padding: 0 0 0 11px; color: #1F4E79;
     border-left: 4px solid #2E75B6; line-height: 1.5; }
h3 { font-size: 1.06rem; font-weight: 700; letter-spacing: -0.02em;
     margin: 1.7em 0 0.5em; color: #334155; line-height: 1.55; }
h2 .q, h3 .q { display: inline-block; font-weight: 400; font-size: 0.72em;
               line-height: 1.5; vertical-align: middle; white-space: normal; }

/* ── 몸통 — 여기부터가 영상에 그대로 들어간다 ──────────────────────────── */

p { line-height: 1.75; margin: 0.45em 0; }

/* ★ 가이드의 「리드(한 줄 요약)」. 첫 문단을 굵은 파랑으로 세워 그 장이 무엇을
   말하는지 한 줄로 먼저 읽히게 한다. **마크업을 안 바꾸고** 자리로만 고른다 —
   원고를 쓰는 쪽(b3)이 한 줄을 더 신경 쓸 필요가 없고, 줄 세기도 안 흔들린다. */
.doc > p:first-child { font-weight: 700; color: #1F4E79; letter-spacing: -0.015em;
                       margin: 0 0 0.7em; }

/* 목록 — 가이드의 「큰 숫자를 연하게」. 기본 불릿을 버리고 연한 파랑 사각형을
   쓴다. 점보다 각이 진 표가 슬라이드에서 또렷하게 읽힌다. */
ul, ol { margin: 0.45em 0 0.85em; padding-left: 0; list-style: none; }
li { position: relative; margin: 0.4em 0; padding-left: 17px; line-height: 1.7; }
li::before { content: ""; position: absolute; left: 0; top: 0.62em;
             width: 7px; height: 7px; background: #9DC3E6; border-radius: 2px; }
ol { counter-reset: n; }
ol > li::before { content: counter(n); counter-increment: n;
                  width: auto; height: auto; top: 0; background: none;
                  color: #CBD5E1; font-weight: 700; font-size: 0.95em; }

/* 강조 — 굵게만 하지 않고 색까지 준다. 가이드가 제목에서 쓰는 2색 규칙을
   본문에서도 같은 뜻으로 반복하는 것이다. */
b, strong { font-weight: 700; color: #1F4E79; }
code { background: #F1F5F9; color: #334155; padding: 1px 5px; border-radius: 3px;
       font-size: 0.92em; }

/* 표 — 가이드 그대로. 머리행 진한 파랑 채움 + 흰 글자, 본문 행 교차, 테두리 연회색 */
table { border-collapse: collapse; width: 100%; margin: 0.6em 0 0.9em;
        font-size: 0.94em; table-layout: fixed; }
th, td { border: 1px solid #E2E8F0; padding: 0.46em 0.66em;
         text-align: left; vertical-align: top; line-height: 1.6; }
th { background: #2E75B6; color: #ffffff; font-weight: 700;
     letter-spacing: -0.01em; border-color: #2E75B6; }
tbody tr:nth-child(even) td, tr:nth-child(even) td { background: #F8FAFC; }
figure { margin: 10px 0; text-align: center; }

/* ★ 근거 쪽 — **접어 둔다.** 눌러야 쪽 범위가 보인다.
   JS 를 쓰지 않는다: 이 원고를 받는 쪽(발표 쇼케이스)이 <script> 를 전부 제거하고
   innerHTML 로 넣기 때문에, JS 로 만들면 안 접힌다. label + checkbox 로 CSS 만
   써서 만든다. <label>·<input>·<b>·<span> 은 전부 phrasing 이라 <h3> 안에 넣어도 된다. */
.q { display: inline; margin-left: 7px; cursor: pointer; user-select: none;
     font-size: .78em; font-weight: 700; color: #94A3B8;
     background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 999px;
     padding: 1px 8px; white-space: nowrap; vertical-align: middle; }
.q:hover { background: #E2E8F0; }
.q > input { position: absolute; opacity: 0; width: 0; height: 0; }
.q > b::before { content: "\\25B8"; margin-right: 3px; font-weight: 400; }
.q > input:checked ~ b::before { content: "\\25BE"; }
.q > .qn { display: none; }
.q > input:checked ~ .qn { display: inline; margin-left: 6px; font-weight: 400;
                           color: #94A3B8; white-space: normal; }
/* 배지 안의 숫자까지 파랗게 굵어지면 안 된다 — 위 `b` 규칙을 여기서만 되돌린다 */
.q b { color: inherit; font-weight: 700; }

/* ★ 그림 높이 상한. **폭만 막으면 안 된다** — 인라인 SVG 는 viewBox 비율대로 폭에
   맞춰 늘어나므로, 가로로 넓은 도식이 화면 절반을 먹는다. `width:auto` +
   `max-height` 로 비율을 지키면서 높이로 자른다. */
svg, img { max-height: 240px; width: auto; max-width: 100%; height: auto;
           display: block; margin: 12px auto 10px; }

/* ★ 어떤 경우에도 가로로 밀지 않는다. 이 원고는 화면이 되므로 마지막 방어선이다. */
* { max-width: 100%; }
body { overflow-x: hidden; overflow-wrap: anywhere; }
""".strip()


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


_LEAD_NO = __import__("re").compile(r"^\s*\d{1,3}(?:\.\d{1,2})*[.)]?\s+")


def slide_label(no: Optional[str], title: Optional[str]) -> str:
    """화면에 뜰 한 줄. **번호를 두 번 적지 않는다.**

    목차의 `no`(예: `5`)를 제목 앞에 붙이는데, 모델이 제목에도 번호를 적어 오면
    「5 5 분기점은 소득 25,000달러」가 된다. 실제로 그렇게 나왔다. 제목이 이미
    번호로 시작하면 그 제목만 쓴다 — 어느 쪽이 맞는지는 사람이 목차 화면에서
    고칠 수 있고, 여기서는 겹치는 것만 막는다.
    """
    n = (no or "").strip()
    t = (title or "").strip()
    if not t:
        return n
    if not n or _LEAD_NO.match(t):
        return t
    return f"{n} {t}"


def page_badge(pages: List[int]) -> str:
    """`.q` 배지 — 접힌 채로는 첫 쪽만, 펴면 범위가 보인다."""
    if not pages:
        return ""
    lo = pages[0]
    hi = pages[-1] if len(pages) > 1 else lo
    span = f"{lo}쪽" if lo == hi else f"{lo}–{hi}쪽"
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
        label = slide_label(s.get("no"), s.get("title"))
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
