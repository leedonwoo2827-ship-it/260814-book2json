# -*- coding: utf-8 -*-
"""B2 장 나누기 — **여기서 장 수가 정해진다.**

`h3` 하나가 슬라이드 한 판이므로, 이 단계가 낸 장 수가 곧 발표의 장 수다.
그래서 뒤의 어떤 단계보다 사람이 확인해야 하는 자리이고, 손편집(`outline_of`)이
붙는 자리도 여기다.

★ 모델이 낸 값을 그대로 믿지 않는다. **코드가 수리한다** — 이름표가 겹치면 새로
  짓고, 그림 종류가 비면 `svg` 로 채우고, 줄 예산이 6을 넘으면 깎는다.
  showcase 의 `s3_caption.py` 가 환각 프레임을 버리고 개수를 다시 맞추는 것과
  같은 태도다. 지어낸 값 하나가 뒤 단계 전부를 조용히 망가뜨린다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from core import book as bk, config, workspace as ws
from llm.claude_provider import ClaudeProvider
from pipeline.registry import STAGES, cached_data, write_cache

MAX_BLOCKS = 6

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"num": {"type": "string"}, "title": {"type": "string"}},
                "required": ["num", "title"],
                "additionalProperties": False,
            },
        },
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "data_id": {"type": "string"},
                    "group": {"type": "string"},
                    "no": {"type": "string"},
                    "title": {"type": "string"},
                    "say": {"type": "string"},
                    "pages": {"type": "array", "items": {"type": "integer"}},
                    "visual": {"type": "string", "enum": ["svg", "table"]},
                    "visual_note": {"type": "string"},
                    "blocks_budget": {"type": "integer"},
                },
                "required": ["data_id", "group", "no", "title", "say", "pages",
                             "visual", "visual_note", "blocks_budget"],
                "additionalProperties": False,
            },
        },
        "dropped": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "groups", "slides", "dropped"],
    "additionalProperties": False,
}

_ID_OK = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")


def build_brief(project: Dict[str, Any], md: str, heads: List[Dict[str, Any]]) -> str:
    """모델에게 보낼 재료 한 덩이.

    ★ 본문을 **자르지 않는다.** 한 장이 4~6만 자(2~3만 토큰)라 통째로 들어간다.
      앞부분만 보내면 뒤쪽 절이 통째로 목차에서 빠지는데, 그것을 사람이 알아채려면
      책과 목차를 나란히 놓고 세어야 한다 — 아무도 안 한다.
    """
    hint = bk.outline_hint(heads)
    budget = int(project.get("slide_budget") or 40)
    prefix = project.get("id_prefix") or "bk"
    lines = [
        f"# 책", project.get("book") or "(제목 없음)",
        f"\n# 이 장", project.get("title") or "(제목 없음)",
        f"\n# 장 예산", f"{budget}장 (±3)",
        f"\n# 이름표 앞머리", f"`{prefix}-` 로 시작할 것 (예: {prefix}-03)",
    ]
    if hint:
        lines += ["\n# 책이 매긴 목차 — 참고만 할 것",
                  "책의 절 하나가 여덟 쪽이면 여덟 장짜리다. 그대로 베끼지 마라.",
                  "```", hint, "```"]
    lines += ["\n# 본문", md]
    return "\n".join(lines)


def repair(raw: Dict[str, Any], prefix: str) -> tuple[Dict[str, Any], List[str]]:
    """모델이 낸 목차를 **거부하지 않고 수리한다.** 무엇을 고쳤는지 남긴다."""
    warn: List[str] = []
    slides: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for i, s in enumerate(raw.get("slides") or [], start=1):
        did = (s.get("data_id") or "").strip().lower()
        if not _ID_OK.match(did) or did in seen:
            # ★ 지어서라도 **반드시** 채운다. 이름표가 없는 장은 그림을 매달 데가
            #   없어서, 원고를 한 번 고치는 순간 그 장의 그림이 미아가 된다.
            new = f"{prefix}-{i:02d}"
            n = i
            while new in seen:
                n += 1
                new = f"{prefix}-{n:02d}"
            warn.append(f"이름표를 새로 지었습니다: {did or '(빈값)'} → {new}")
            did = new
        seen.add(did)

        vis = s.get("visual")
        if vis not in ("svg", "table"):
            # 줄글만 있는 화면을 만들지 않는 것이 이 원고의 목적이다. 비면 그림이다.
            warn.append(f"{did}: 그림 종류가 비어 svg 로 채웠습니다")
            vis = "svg"

        budget = int(s.get("blocks_budget") or 4)
        if budget > MAX_BLOCKS:
            warn.append(f"{did}: 줄 예산 {budget} → {MAX_BLOCKS} (한 판에 6줄 이내)")
            budget = MAX_BLOCKS
        budget = max(1, budget)

        pages = [int(p) for p in (s.get("pages") or []) if isinstance(p, int)]
        slides.append({
            "data_id": did,
            "group": (s.get("group") or "").strip(),
            "no": (s.get("no") or "").strip(),
            "title": (s.get("title") or "").strip(),
            "say": (s.get("say") or "").strip(),
            "pages": pages[:2],
            "visual": vis,
            "visual_note": (s.get("visual_note") or "").strip(),
            "blocks_budget": budget,
        })

    groups = [{"num": str(g.get("num") or ""), "title": (g.get("title") or "").strip()}
              for g in (raw.get("groups") or [])]
    # 아무 장도 안 딸린 묶음은 목차에 갈래만 만들고 아무것도 안 담는다 — 뺀다.
    used = {s["group"] for s in slides}
    kept = [g for g in groups if g["num"] in used]
    if len(kept) != len(groups):
        warn.append(f"장이 없는 묶음 {len(groups) - len(kept)}개를 뺐습니다")

    return {"title": (raw.get("title") or "").strip(), "groups": kept,
            "slides": slides, "dropped": [str(x) for x in (raw.get("dropped") or [])]}, warn


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["b2-outline"]
    cfg = config.load()
    src = cached_data(pid, slug, "b1-pdf") or {}
    md_file = src.get("md_file")
    if not md_file or not Path(md_file).is_file():
        raise RuntimeError("책에서 글 뽑기(b1-pdf)를 먼저 돌리세요")

    md = Path(md_file).read_text(encoding="utf-8")
    system = (Path(__file__).resolve().parent.parent
              / "llm" / "prompts" / "outline.md").read_text(encoding="utf-8")
    prefix = project.get("id_prefix") or "bk"

    job.progress(0, 1, "목차 세우는 중")
    p = ClaudeProvider(
        model=(project.get("models") or {}).get("outline") or cfg["models"]["outline"],
        effort=cfg["effort"]["outline"],
        budget_usd=cfg["budget_usd"]["per_stage"],
        on_activity=lambda s: job.progress(0, 1, s),
    )
    raw = p.structured(system, [{"role": "user",
                                 "content": build_brief(project, md, src.get("heads") or [])}],
                       schema=SCHEMA)
    job.progress(1, 1, "정리")

    data, warn = repair(raw, prefix)
    if not data["slides"]:
        raise RuntimeError("장이 하나도 안 나왔습니다. 본문이 제대로 뽑혔는지 확인하세요")

    ws.write_json(ws.outline_path(pid, slug, create=True), data)

    n_tab = sum(1 for s in data["slides"] if s["visual"] == "table")
    job.add_log(f"{len(data['slides'])}장 · 묶음 {len(data['groups'])}개 "
                f"· 그림 {len(data['slides']) - n_tab}개 · 표 {n_tab}개 · ${p.last_cost_usd:.3f}")
    for line in data["dropped"][:6]:
        job.add_log(f"버림: {line}")
    for w in warn[:8]:
        job.add_log(w)

    return write_cache(pid, slug, "b2-outline",
                       input_hash=stage.input_hash(pid, slug, project),
                       data=data, code_version=stage.code_version,
                       model=p.model, cost_usd=p.last_cost_usd,
                       status="degraded" if warn else "ok", warnings=warn)


STAGES["b2-outline"].run = run
