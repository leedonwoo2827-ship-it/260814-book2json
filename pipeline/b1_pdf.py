# -*- coding: utf-8 -*-
"""B1 책에서 글 뽑기 — **결정론. 돈이 안 든다.**

PDF 는 안 바뀐다. 그래서 이 단계는 몇 번을 돌려도 같은 것을 내고, 다시 돌리는
데 값을 치르지 않는다. 뒤 단계가 비싸므로 **여기서 최대한 걸러 둔다** — 머리글과
쪽번호가 본문에 섞여 들어가면 모델은 그것도 내용인 줄 알고 요약에 넣는다.

내는 것 두 가지:

    01_원문/pages.json   쪽별 원본 — 무엇을 잘랐는지 사람이 확인하는 자리
    01_원문/본문.md      이어 붙인 본문 — b2·b3 이 실제로 읽는 것

★ 자르는 규칙 자체는 `core/book.py` 에 있다. 여기는 **그것을 프로젝트에 앉히는**
  일만 한다 — 여러 파일을 이어 붙이고, 숫자를 세고, 캐시 봉투에 담는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core import book as bk, workspace as ws
from pipeline.registry import STAGES, write_cache


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["b1-pdf"]
    paths = [Path(p) for p in (project.get("pdfs") or [])]
    if not paths:
        raise RuntimeError("읽을 PDF 가 없습니다. 새 원고 화면에서 폴더나 파일을 넣으세요")

    head = int(project.get("drop_head") or 0)
    tail = int(project.get("drop_tail") or 0)

    d = ws.step_dir(pid, slug, "source")
    parts: List[str] = []
    heads: List[Dict[str, Any]] = []
    raw: List[Dict[str, Any]] = []
    warn: List[str] = []

    for i, p in enumerate(paths):
        job.progress(i, len(paths), p.name)
        if not p.is_file():
            warn.append(f"파일이 없습니다: {p}")
            continue
        b = bk.read_pdf(p, drop_head=head, drop_tail=tail)
        md, hs = bk.to_markdown(b)
        parts.append(md)
        heads.extend(hs)
        raw.append({
            "file": b["file"], "pages": len(b["pages"]),
            "body_size": b["body_size"], "head_sizes": b["head_sizes"],
            # 쪽별 원문은 **줄 목록 그대로** 남긴다. 이어 붙인 본문만 두면 나중에
            # "이 문장이 원래 몇 쪽 어디였나" 를 되짚을 방법이 없다.
            "page_list": [{"idx": pg["idx"], "no": pg["no"],
                           "body": [" ".join(x["lines"]) for x in pg["body"]],
                           "side": [" ".join(x["lines"]) for x in pg["side"]]}
                          for pg in b["pages"]],
        })

    if not parts:
        raise RuntimeError("읽어 낸 쪽이 하나도 없습니다. 경로와 앞·뒤 버릴 쪽 수를 확인하세요")

    md = "\n\n".join(parts)
    ws.write_json(d / "pages.json", {"files": raw})
    ws.write_text(d / "본문.md", md)

    pages = sum(f["pages"] for f in raw)
    by_level = {lv: sum(1 for h in heads if h["level"] == lv) for lv in (1, 2, 3, 4)}
    job.add_log(f"{len(raw)}개 파일 · {pages}쪽 · {len(md):,}자")
    job.add_log("책이 매긴 제목: "
                + " · ".join(f"{lv}단 {n}개" for lv, n in by_level.items() if n))
    job.add_log(f"본문: {d / '본문.md'}")
    if not heads:
        # 못 찾아도 멈추지 않는다 — b2 는 본문 전체를 읽고 스스로 나눌 수 있다.
        # 다만 **사람에게 알린다.** 목차가 이상하게 나오면 여기가 원인이다.
        warn.append("책에서 제목을 하나도 못 찾았습니다. b2 가 본문만 보고 나눕니다")

    return write_cache(
        pid, slug, "b1-pdf",
        input_hash=stage.input_hash(pid, slug, project),
        data={"dir": str(d), "files": [f["file"] for f in raw],
              "pages": pages, "chars": len(md), "heads": heads,
              "md_file": str(d / "본문.md")},
        code_version=stage.code_version,
        status="degraded" if warn else "ok", warnings=warn)


STAGES["b1-pdf"].run = run
