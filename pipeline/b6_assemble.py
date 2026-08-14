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

from typing import Any, Dict, List

from core import workspace as ws
from pipeline.registry import STAGES, cached_data, outline_of, write_cache
from render import manuscript as ms


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
    ledger = (ws.load_ledger(pid, slug).get("by_id") or {})
    slides = order_slides(outline, draft)
    if not slides:
        raise RuntimeError("목차와 몸통이 안 맞습니다. 목차를 고쳤다면 몸통을 다시 쓰세요")

    orphan = [k for k in draft if k not in {s["data_id"] for s in slides}]
    title = project.get("title") or outline.get("title") or slug

    html = ms.build(title=title, book=project.get("book") or "",
                    groups=outline.get("groups") or [], slides=slides,
                    figures=figures,
                    prompts={s["data_id"]: ledger.get(s["data_id"]) or {} for s in slides})

    d = ws.step_dir(pid, slug, "export")
    path = d / f"{ws.ascii_slug(slug) or 'manuscript'}_원고.html"
    ws.write_text(path, html)

    lines = sum(len(s["blocks"]) for s in slides)
    n_fig = sum(1 for s in slides if figures.get(s["data_id"]))
    n_tab = sum(1 for s in slides if any(b["kind"] == "table" for b in s["blocks"]))
    bare = [s["data_id"] for s in slides
            if not figures.get(s["data_id"])
            and not any(b["kind"] == "table" for b in s["blocks"])]
    n_img = sum(1 for s in slides if (ledger.get(s["data_id"]) or {}).get("prompt"))

    warn: List[str] = []
    if bare:
        warn.append(f"그림도 표도 없는 장 {len(bare)}개")
    if orphan:
        warn.append(f"목차에 없어 안 실린 몸통 {len(orphan)}개: {', '.join(orphan[:6])}")

    job.add_log(f"{len(slides)}장 · 줄 {lines}개 · 그림 {n_fig}개 · 표 {n_tab}장 "
                f"· 그림 지시문 {n_img}개")
    job.add_log(f"원고: {path}  ({path.stat().st_size / 1024:.0f}KB)")
    if bare:
        job.add_log(f"그림도 표도 없는 장: {', '.join(bare[:10])} — b4 를 다시 돌리세요")

    return write_cache(pid, slug, "b6-assemble",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"file": str(path), "slides": len(slides), "lines": lines,
                             "figures": n_fig, "tables": n_tab, "bare": bare,
                             "order": [s["data_id"] for s in slides]},
                       code_version=stage.code_version,
                       status="degraded" if warn else "ok", warnings=warn)


STAGES["b6-assemble"].run = run
