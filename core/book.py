# -*- coding: utf-8 -*-
"""단행본 PDF → 본문 텍스트. **책을 읽는 유일한 자리.**

Claude 에게 보낼 재료를 만드는 곳이다. 여기서 흘린 쓰레기(머리글·쪽번호·여백
용어상자)는 뒤에서 못 걸러진다 — 모델은 그것도 본문인 줄 알고 요약에 섞는다.
그래서 **자르는 규칙을 한 곳에 모으고, 무엇을 잘랐는지 숫자로 남긴다.**

새뮤얼슨 『경제학』 5~7부(13개 장, 30~44쪽)를 재어 만든 규칙이다.

    쪽 배치      짝수쪽 본문 x0≈212 · 여백상자 x≈57
                 홀수쪽 본문 x0≈79  · 여백상자 x≈454
                 → **어느 한쪽으로 못 박지 않는다.** 쪽마다 블록 x0 의 최빈값을
                   본문 단으로 잡는다. 다른 판형에서도 그대로 돈다.
    머리글       위 60pt · 아래 690pt 밖 (「제19장 거시경제학 개요」 · 쪽번호)
    글자 크기    본문 10.5pt · 작은 절 14pt · 절 16pt · 큰 절 17.5pt

★ 제목은 **번호가 아니라 글자 크기로** 찾는다.
  처음엔 「1.」 「1.1.」 같은 번호로 찾았다. 두 방향에서 다 틀렸다.
    가짜를 주웠다  — 이 책은 문단을 번호로 늘어놓는다(「1. 재정정책은 정부지출과
                    과세, 두 가지다. …」). 19장 한 장에서 진짜 4개에 가짜 12개.
    진짜를 놓쳤다  — 21장의 절 제목은 「20세기 소비의 진화」처럼 번호가 없다.
                    13개 장 중 4개 장에서 제목을 **하나도** 못 찾았다.
  크기는 판면이 정한 값이라 둘 다 안 생긴다. 번호는 이제 제목을 찾는 데 안 쓰고,
  찾은 제목 앞에 붙어 있으면 떼어서 `num` 에 담기만 한다.

여백 용어상자(`총공급[aggregate supply] 일정한 기간 동안…`)는 **버리지 않고
따로 담는다.** 그 책이 중요하다고 표시해 둔 용어 정의라 원고에 그대로 쓸 값이
있는데, 본문에 섞으면 문단 한가운데서 말이 끊긴다.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 판면 밖 — 머리글·쪽번호가 사는 띠. 본문은 이 사이에만 있다.
TOP, BOTTOM = 60.0, 690.0
# 본문 단으로 볼 x0 허용 오차. 문단 첫 줄이 10pt 들여쓰기되므로 그보다 커야 한다.
COL_TOL = 34.0
# 본문보다 이만큼은 커야 제목으로 본다. 1.15 면 10.5pt 본문에서 12.1pt 위.
HEAD_RATIO = 1.15
# 제목은 이름이지 문장이 아니다. 크기만 보면 강조된 긴 인용문이 딸려 온다.
TITLE_MAX = 44

# 제목 앞에 붙은 번호 — 찾는 데는 안 쓰고, 찾은 뒤 떼어 내는 데만 쓴다.
_NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)\.\s*(\S.*)$")
# 그림·표 설명은 제목과 크기가 겹친다(둘 다 14~16pt). 말머리로 가른다.
_CAPTION = re.compile(r"^(그림|표|사례|사례연구)\s*[\d〈<]")

# 문장이 끝났다고 볼 자리. 여기서 안 끊기면 다음 줄과 이어 붙인다.
_END = tuple(".?!…:;”』」》)]")
_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ一-鿿]")
# 라틴 낱말이 줄 끝에서 잘린 자리 — `fab-\nulous`
_HYPHEN = re.compile(r"([A-Za-z])-$")
_NUM_ONLY = re.compile(r"^\d{1,4}$")


def _is_cjk(ch: str) -> bool:
    return bool(_HANGUL.match(ch or ""))


def join_lines(lines: List[str]) -> List[str]:
    """줄바꿈으로 잘린 문장을 되붙인다.

    ★ 한글과 라틴을 다르게 잇는다. 한글은 낱말 한가운데서 줄이 바뀌므로 **붙여야**
      하고(사이에 공백을 넣으면 「경제학 자들」이 된다), 라틴은 낱말 사이에서
      바뀌므로 **띄어야** 한다. 한쪽 규칙만 쓰면 반대쪽이 전부 깨진다.
    """
    out: List[str] = []
    for raw in lines:
        s = (raw or "").strip()
        if not s:
            continue
        if not out:
            out.append(s)
            continue
        prev = out[-1]
        if prev.endswith(_END) or prev.endswith("다"):
            out.append(s)
            continue
        if _HYPHEN.search(prev):
            out[-1] = prev[:-1] + s                   # fab- + ulous → fabulous
            continue
        glue = "" if (_is_cjk(prev[-1]) and _is_cjk(s[0])) else " "
        out[-1] = prev + glue + s
    return out


# ── 쪽 하나 읽기 ───────────────────────────────────────────────────────────
def _blocks(page) -> List[Dict[str, Any]]:
    """판면 안의 글 덩이. 각 덩이의 **가장 큰 글자 크기**를 같이 담는다.

    크기를 최댓값으로 잡는 이유: 제목 줄이 「1.1. 」(16pt) + 「소비와 소득」(16pt)
    처럼 여러 span 으로 쪼개져 오는데, 그중 하나라도 크면 그 줄은 제목이다.
    평균을 내면 뒤에 붙은 작은 각주 기호 하나에 끌려 내려간다.
    """
    out: List[Dict[str, Any]] = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:                        # 그림 덩이 — 글이 없다
            continue
        x0, y0 = b["bbox"][0], b["bbox"][1]
        if not (TOP < y0 < BOTTOM):                   # 머리글·쪽번호 띠
            continue
        lines, size = [], 0.0
        for ln in b.get("lines", []):
            txt = "".join(s["text"] for s in ln["spans"]).strip()
            if txt:
                lines.append(txt)
                size = max(size, max(s["size"] for s in ln["spans"]))
        if lines:
            out.append({"x0": x0, "y0": y0, "lines": lines, "size": round(size, 1)})
    return out


def _body_size(pages: List[List[Dict[str, Any]]]) -> float:
    """본문 글자 크기 — **글자 수로 가중한** 최빈값.

    덩이 수로 세면 안 된다. 제목은 한 줄짜리 덩이가 많아서 수로는 본문과 겨룰 만한데,
    글자 수로 세면 본문이 압도적이다(19장 실측: 10.5pt 가 39,000자, 16pt 가 300자).
    """
    c: Counter = Counter()
    for blocks in pages:
        for b in blocks:
            c[b["size"]] += sum(len(x) for x in b["lines"])
    return c.most_common(1)[0][0] if c else 10.5


def _printed_no(page) -> int:
    """책에 찍힌 쪽번호. 판면 밖(위·아래 띠)의 숫자만 있는 덩이에서 찾는다.

    이것을 쓰는 이유는 사람이 대조할 수 있어야 하기 때문이다. 원고에 「원서
    412쪽」이라 적어 두면 책을 펴서 바로 확인할 수 있는데, PDF 상의 쪽수를 적으면
    그 대조가 안 된다(앞에 속표지가 몇 장 붙었는지 사람이 알 수 없다).
    """
    for b in page.get_text("blocks"):
        if b[6] == 0 and (b[1] <= TOP or b[1] >= BOTTOM):
            s = (b[4] or "").strip()
            if _NUM_ONLY.match(s):
                return int(s)
    return 0


def read_pdf(path: Path, *, drop_head: int = 0, drop_tail: int = 0) -> Dict[str, Any]:
    """PDF 한 장(章) → 쪽별 본문 + 제목 크기 사다리.

    `drop_head`/`drop_tail` 은 속표지·판권처럼 **사람이 보고 정하는** 값이다.
    자동으로 알아내려 들지 않는다 — 틀리면 본문 첫 쪽이 조용히 사라진다.
    """
    import fitz                                       # PyMuPDF. 무거워서 여기서 import

    doc = fitz.open(str(path))
    lo, hi = max(0, drop_head), len(doc) - max(0, drop_tail)
    raw = [(i, doc[i]) for i in range(lo, hi)]
    per_page = [_blocks(pg) for _, pg in raw]
    body = _body_size(per_page)

    pages: List[Dict[str, Any]] = []
    for (i, page), blocks in zip(raw, per_page):
        if not blocks:
            pages.append({"idx": i + 1, "no": _printed_no(page) or (i + 1),
                          "body": [], "side": []})
            continue
        # ★ 본문 단의 x 좌표를 **쪽마다 다시 잰다.** 이 책은 짝수쪽과 홀수쪽 판면이
        #   좌우로 뒤집혀 있어서(짝수 212 · 홀수 79), 한 번 재서 문서 전체에 쓰면
        #   절반이 통째로 여백으로 분류된다.
        col = Counter(round(b["x0"] / 20) * 20 for b in blocks).most_common(1)[0][0]
        main, side = [], []
        for b in sorted(blocks, key=lambda b: (round(b["y0"]), b["x0"])):
            (main if abs(b["x0"] - col) <= COL_TOL else side).append(b)
        pages.append({"idx": i + 1, "no": _printed_no(page) or (i + 1),
                      "body": main, "side": side})
    doc.close()

    # 제목 크기 사다리 — 큰 것부터. 본문보다 크고, 짧고, 그림·표 설명이 아닌 덩이만.
    sizes = sorted({b["size"] for pg in pages for b in pg["body"]
                    if _is_head(b, body)}, reverse=True)
    return {"file": path.name, "pages": pages, "body_size": body, "head_sizes": sizes}


def _is_head(block: Dict[str, Any], body_size: float) -> bool:
    if block["size"] < body_size * HEAD_RATIO:
        return False
    text = " ".join(block["lines"]).strip()
    return bool(text) and len(text) <= TITLE_MAX and not _CAPTION.match(text)


def to_markdown(book: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """쪽별 본문 → 사람이 읽고 Claude 가 받는 마크다운 하나 + 제목 목록.

    쪽 표시를 `<!-- p.412 -->` 로 본문에 박아 둔다. 이래야 모델이 「이 내용은
    412쪽」이라고 말할 근거가 생긴다. 근거 없이 쪽수를 쓰게 하면 지어낸다.
    """
    body_size = book["body_size"]
    # ★ 순위만으로 층을 매기면 장마다 뜻이 달라진다. 어떤 장은 표제(32pt)가 있고
    #   어떤 장은 없어서, 순위 1등이 「장 제목」이었다가 「절 제목」이었다가 한다.
    #   그래서 **표제만 절대 크기로 먼저 떼어** 낸다(본문의 2배 이상). 남은 것들만
    #   순위로 h2 · h3 · h4 를 매기면 열세 장이 같은 뜻으로 읽힌다.
    #   네 단째부터는 전부 h4 다 — 원고 규약이 쓰는 층은 h2(묶음)·h3(장) 둘뿐이고,
    #   그보다 잘게 나뉜 것은 장 안의 소제목이라 몸통으로 들어간다.
    rest = [s for s in book["head_sizes"] if s < body_size * 2.0]
    level_of = {s: 1 for s in book["head_sizes"] if s >= body_size * 2.0}
    level_of.update({s: min(2 + i, 4) for i, s in enumerate(rest)})

    chunks: List[str] = []
    heads: List[Dict[str, Any]] = []
    for pg in book["pages"]:
        if not pg["body"] and not pg["side"]:
            continue
        chunks.append(f"<!-- p.{pg['no']} -->")
        for b in pg["body"]:
            text = " ".join(join_lines(b["lines"])).strip()
            if not text:
                continue
            if _is_head(b, body_size) and b["size"] in level_of:
                lv = level_of[b["size"]]
                num, title = "", text
                if m := _NUMBERED.match(text):
                    num, title = m.group(1), m.group(2).strip()
                heads.append({"level": lv, "num": num, "title": title,
                              "page": pg["no"], "size": b["size"]})
                chunks.append("#" * lv + " " + text)
            elif _CAPTION.match(text):
                chunks.append(f"> [그림·표] {text}")
            else:
                chunks.extend(join_lines(b["lines"]))
        # 여백 칸에는 용어상자만 있는 게 아니다 — 그림 설명·인용구·각주도 같이 온다.
        # 무엇인지 단정하지 말고 **여백에서 왔다는 사실만** 표시한다.
        for b in pg["side"]:
            for s in join_lines(b["lines"]):
                chunks.append(f"> [여백] {s}")
    return "\n\n".join(chunks) + "\n", heads


_PAGE_MARK = re.compile(r"^<!-- p\.(\d+) -->$", re.M)


def split_pages(md: str) -> Dict[int, str]:
    """`본문.md` → {쪽번호: 그 쪽의 글}.

    b3 은 장마다 **그 장의 근거 쪽만** 보낸다. 한 장을 쓰자고 5만 자를 통째로
    다시 보내면 여덟 장짜리 묶음 하나에 40만 자가 들어간다 — 값도 값이지만,
    모델이 엉뚱한 쪽의 내용을 그 장에 섞는다.
    """
    marks = list(_PAGE_MARK.finditer(md))
    out: Dict[int, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(md)
        out[int(m.group(1))] = md[m.end():end].strip()
    return out


def pages_text(by_page: Dict[int, str], lo: int, hi: int, *, pad: int = 1) -> str:
    """`[lo, hi]` 쪽의 글. 앞뒤로 `pad` 쪽씩 더 준다.

    더 주는 이유: 문단이 쪽 경계에서 잘린다. 딱 맞게 자르면 그 장의 마지막 문장이
    반만 들어와서, 모델이 뒷말을 지어내거나 그 대목을 통째로 빠뜨린다.
    """
    if not by_page:
        return ""
    if not (lo and hi):
        lo, hi = min(by_page), max(by_page)
    keys = [n for n in sorted(by_page) if lo - pad <= n <= hi + pad]
    return "\n\n".join(f"<!-- p.{n} -->\n{by_page[n]}" for n in keys)


def outline_hint(heads: List[Dict[str, Any]], *, limit: int = 90) -> str:
    """b2-outline 브리프에 넣을 **책 스스로의 목차.** 없으면 빈 문자열."""
    if not heads:
        return ""
    rows = [f"{'  ' * (h['level'] - 2)}{(h['num'] + '. ') if h['num'] else ''}"
            f"{h['title']}  (p.{h['page']})" for h in heads[:limit]]
    return "\n".join(rows)
