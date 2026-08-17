# -*- coding: utf-8 -*-
"""B6 원고 조립 — **결정론. 돈이 안 든다.**

앞 단계들이 낸 조각(목차 · 몸통 · 그림 · 프롬프트)을 파일 하나로 묶는다.
Claude 를 부르지 않으므로 마음껏 다시 돌려도 된다 — 목차를 손으로 고칠 때마다
여기만 다시 누르면 된다.

★ 장의 **순서는 목차가 정한다.** b3 이 장을 쪼갰으면(`sam-19-03` → `…-03b`)
  원래 장 바로 뒤에 꽂는다. 몸통 dict 의 키 순서를 믿으면 안 된다 — 묶음 하나가
  실패했다가 다시 돌면 그 장들이 맨 뒤로 간다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from core import narration as nr, speech, workspace as ws
from pipeline.registry import STAGES, cached_data, outline_of, write_cache
from render import manuscript as ms


def bookends(outline: Dict[str, Any], title: str, book: str) -> tuple[str, str]:
    """표지와 마무리에서 할 말. **목차가 써 두었으면 그것, 없으면 목차로 짓는다.**

    ★ 지어내는 쪽은 모델을 안 부른다. 이미 있는 재료(장 제목·묶음 이름)만 이어 붙인다
      — 없는 말을 지어내지 않으려는 것이고, 목차를 다시 돌리지 않고도(그게 $1 짜리다)
      앞뒤 대본이 생기게 하려는 것이다. 다음 장부터는 b2 가 직접 써서 온다.
    """
    intro = (outline.get("intro") or "").strip()
    outro = (outline.get("outro") or "").strip()
    names = [g.get("title", "").strip() for g in (outline.get("groups") or [])
             if g.get("title")]
    what = ", ".join(names[:4]) + (" 순으로" if names else "")

    # 말투는 **하십시오체**다 — 아바타가 읽는 글이라 「~이다」로 끝나면 반말처럼
    # 들린다(2026-08-14 지적). `llm/prompts/outline.md` 의 `say` 규칙과 같다.
    if not intro:
        intro = (f"{book + ' ' if book else ''}{title} 입니다. "
                 + (f"{what} 살펴보겠습니다. " if names else "")
                 + "화면마다 핵심을 한 줄씩 짚고, 그 뒤에 있는 이야기를 함께 풀어 "
                   "보겠습니다.")
    if not outro:
        outro = (f"여기까지 {title} 이었습니다. "
                 + (f"{names[0]}에서 시작해 {names[-1]}까지 왔습니다. "
                    if len(names) > 1 else "")
                 + "다음 장에서 이어가겠습니다.")
    return intro, outro


def script_text(*, title: str, book: str, minutes: int, verdict: Dict[str, Any],
                slides: List[Dict[str, Any]],
                intro: str = "", outro: str = "") -> str:
    """읽는 대본. **원고 안의 `data-say` 를 사람이 읽는 모양으로 편 것.**

    원고 HTML 에 이미 다 들어 있는데 왜 따로 내는가 — `data-say` 는 속성이라 파일을
    열어도 안 보인다. 영상 길이를 정하는 것이 바로 그 글인데, 정작 눈으로 훑을
    방법이 없으면 짧은지 긴지도 나중에야 안다. 여기서 장마다 몇 자·몇 초인지 같이
    적어 두면, 어느 장이 얇은지가 목록에서 그대로 보인다.
    """
    head = [f"{title}", f"{book}" if book else "",
            f"목표 {minutes}~{round(minutes * nr.RANGE_MAX)}분 · 지금 {verdict['clock']} "
            f"({verdict['say_chars']:,}자 · {nr.CHARS_PER_MIN}자/분 = 5.5자/초 기준)",
            "AI 아바타가 이 글을 그대로 읽습니다. 고치면 원고(b6)를 다시 조립하세요.",
            "「자막」은 화면에 뜨는 글, 「발음」은 TTS 에 넣을 글입니다 — 뜻은 같고",
            "숫자와 약어의 표기만 다릅니다. 발음 줄이 없으면 바꿀 것이 없었던 것입니다.",
            "─" * 60, ""]

    def one(tag: str, sub: str, text: str) -> List[str]:
        n = nr.count(text)
        out = [tag, f"     {sub} · {n}자 · {n / nr.CHARS_PER_MIN * 60:.0f}초",
               f"자막  {text}" if text else "(비었습니다)"]
        if text and (read := speech.to_read(text)) != text:
            out.append(f"발음  {read}")
        return out + [""]

    # 표지 → 본문 → 마무리. **읽는 순서 그대로** 적는다.
    body: List[str] = one("[표지]", "쇼케이스가 앞에 붙이는 장", intro) if intro else []
    for i, s in enumerate(slides, start=1):
        say = (s.get("say") or "").strip()
        label = ms.slide_label(s.get("no"), s.get("title"))
        # ★ 앞머리는 `[01]` 로 둔다. 제목에 이미 「1.」 이 붙어 있어서 번호를 또 적으면
        #   「1. 1. 경제 전체를…」 이 된다 — 실제로 그렇게 나왔다.
        body += one(f"[{i:02d}] {label}", s["data_id"], say)
    if outro:
        body += one("[마무리]", "쇼케이스가 뒤에 붙이는 장", outro)
    return "\n".join([x for x in head if x] + [""] + body) + "\n"


def order_slides(outline: Dict[str, Any], draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    """목차 순서대로, 쪼갠 장은 원래 장 뒤에. 몸통이 없는 장은 뺀다."""
    out: List[Dict[str, Any]] = []
    extra: Dict[str, List[str]] = {}
    for did, body in draft.items():
        base = body.get("from") or did
        if base != did:
            extra.setdefault(base, []).append(did)

    for s in outline.get("slides") or []:
        did = s["data_id"]
        for k in [did] + sorted(extra.get(did, [])):
            body = draft.get(k)
            if not body:
                continue
            out.append({**s, "data_id": k,
                        "title": body.get("title") or s.get("title") or "",
                        "blocks": body.get("blocks") or []})
    return out


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["b6-assemble"]
    outline = outline_of(pid, slug)
    draft = (cached_data(pid, slug, "b3-write") or {}).get("slides") or {}
    if not draft:
        raise RuntimeError("몸통 쓰기(b3-write)를 먼저 돌리세요")

    figures = (cached_data(pid, slug, "b4-figure") or {}).get("figures") or {}
    slides = order_slides(outline, draft)
    if not slides:
        raise RuntimeError("목차와 몸통이 안 맞습니다. 목차를 고쳤다면 몸통을 다시 쓰세요")

    orphan = [k for k in draft if k not in {s["data_id"] for s in slides}]
    title = project.get("title") or outline.get("title") or slug
    book = project.get("book") or ""
    intro, outro = bookends(outline, title, book)

    # ★ 원고 맨 위에 박을 한 줄을 **여기서 짓는다.** 길이를 아는 자리가 여기라서다.
    src = cached_data(pid, slug, "b1-pdf") or {}
    want = nr.plan_of(project, int(src.get("chars") or 0))
    said = nr.count_all([s.get("say") or "" for s in slides] + [intro, outro])
    # 「제20장」 → 「20장」. 받는 쪽이 장 번호로 파일을 가른다.
    chap = (re.search(r"\d+\s*장", title) or [None])[0] or title
    lecture = nr.label(want, said, chapter=chap)

    html = ms.build(title=title, book=book,
                    groups=outline.get("groups") or [], slides=slides,
                    figures=figures, intro=intro, outro=outro, lecture=lecture)

    d = ws.step_dir(pid, slug, "export")
    stem = ws.ascii_slug(slug) or "manuscript"
    path = d / f"{stem}_원고.html"
    ws.write_text(path, html)

    # ── 길이 — **여기서 처음으로 「몇 분짜리인가」가 확정된다** ──────────────
    #   표지와 마무리도 소리가 나는 글이라 위에서 셀 때 같이 넣었다.
    length = nr.verdict(said, want)
    # ★ 넘기는 파일은 **원고 하나뿐**이다. 나머지는 `bak/` 으로 내린다
    #   (2026-08-14: "필요없는건 bak 폴더로 다 치워줘요. 헷갈려요").
    #   대본은 버리지 않는다 — 아바타가 읽을 글을 사람이 한 번에 통독하는 유일한
    #   자리다. 다만 넘길 것과 같은 칸에 두면 무엇을 주는지가 흐려진다.
    bak = d / "bak"
    script = bak / f"{stem}_대본.txt"
    ws.write_text(script, script_text(title=title, book=book,
                                      minutes=want["minutes"], verdict=length,
                                      slides=slides, intro=intro, outro=outro))

    lines = sum(len(s["blocks"]) for s in slides)
    n_fig = sum(1 for s in slides if figures.get(s["data_id"]))
    n_tab = sum(1 for s in slides if any(b["kind"] == "table" for b in s["blocks"]))
    bare = [s["data_id"] for s in slides
            if not figures.get(s["data_id"])
            and not any(b["kind"] == "table" for b in s["blocks"])]

    warn: List[str] = []
    # ★ 그림이 없는 것은 **경고가 아니다.** 그림 단계(b4)를 아직 안 돌렸을 뿐이고,
    #   조립은 그것과 무관하게 제대로 됐다(2026-08-14 지적). 아래 로그로만 말한다.
    if orphan:
        warn.append(f"목차에 없어 안 실린 몸통 {len(orphan)}개: {', '.join(orphan[:6])}")
    # ★ 길이가 모자란 것은 **경고다.** 원고는 멀쩡해 보이는데 영상만 짧게 나오는
    #   종류의 잘못이라, 여기서 말하지 않으면 영상을 만든 뒤에나 안다.
    if length["short"]:
        warn.append(length["note"])

    job.add_log(f"{len(slides)}장 · 줄 {lines}개 · 그림 {n_fig}개 · 표 {n_tab}장")
    job.add_log(f"대본 {said:,}자 → {length['clock']} "
                f"(목표 {want['minutes']}분 · {length['pct']}%)")
    job.add_log(f"원고: {path}  ({path.stat().st_size / 1024:.0f}KB)")
    job.add_log(f"대본: {script}")
    if length["short"]:
        job.add_log("짧습니다 — 목차 화면에서 장마다 말을 채우거나, 목표 길이를 "
                    "다시 정하고 2번(장 나누기)부터 다시 돌리세요")
    if bare:
        job.add_log(f"아직 그림이 없는 장 {len(bare)}개 — 3번의 그림 단계를 돌리면 채워집니다")

    return write_cache(pid, slug, "b6-assemble",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"file": str(path), "script": str(script),
                             "slides": len(slides), "lines": lines,
                             "figures": n_fig, "tables": n_tab, "bare": bare,
                             "length": length, "want": want,
                             "order": [s["data_id"] for s in slides]},
                       code_version=stage.code_version,
                       status="degraded" if warn else "ok", warnings=warn)


STAGES["b6-assemble"].run = run
