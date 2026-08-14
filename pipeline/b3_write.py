# -*- coding: utf-8 -*-
"""B3 몸통 쓰기 — **가장 비싼 단계.**

장마다 화면에 뜰 줄을 쓴다. 한 장씩 부르면 호출이 60번이라 느리고 비싸고, 한 번에
다 부르면 뒤쪽 장이 뭉개진다(출력이 길어질수록 마지막 장의 품질이 떨어진다).
그래서 **여덟 장씩 묶어** 부른다. 묶음마다 그 장들의 근거 쪽 원문만 실어 보낸다.

★ **줄이 넘쳐도 자르지 않는다.** 예전엔 잘랐다 — 「줄 예산 5를 넘겨 뒤를 잘랐습니다」.
  틀린 태도였다(2026-08-14 지적). 이유 셋:

  1. `blocks_budget` 은 규약이 아니다. b2 가 본문을 보고 **짐작한 수**다. 진짜 규약은
     944 × 507px 이고 그건 b7 이 브라우저에 띄워 **실제로 잰다.** 짐작을 근거로
     내용을 지우면, 지운 쪽이 맞았는지 아무도 모른다.
  2. 지워진 줄은 **되찾을 수 없다.** 캐시에는 수리한 뒤의 것만 남아서, 잘린 문장을
     다시 보려면 그 장을 통째로 다시 써야 한다($2 짜리 단계다).
  3. 조용히 틀린다. 원고는 멀쩡해 보이고, 빠진 것은 책과 나란히 놓고 세어야 보인다.

  그래서 지금은 **다 싣고 말한다.** 넘치면 b7 이 그 장을 `over`/`longer` 로 잡고
  「h3 를 하나 더 만들어 나누세요」라고 적어 준다 — 자르는 것과 나누는 것은 다르다.

★ 태그는 여전히 코드가 씻는다. 모델은 `style=` 이나 `<div>` 를 곧잘 끼워 넣는데,
  규약이 허용하는 것은 `b·code·br·sub·sup` 뿐이다. 남겨 두면 조립본이 원고 CSS 를
  벗어난다. **글자를 지우는 것과 태그를 벗기는 것은 다른 일이다.**

★ 태그도 코드가 씻는다. 모델은 `style=` 이나 `<div>` 를 곧잘 끼워 넣는데, 규약이
  허용하는 것은 `b·code·br·sub·sup` 뿐이다. 남겨 두면 조립본이 원고 CSS 를 벗어난다.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Dict, List

from core import book as bk, config, workspace as ws
from llm.claude_provider import ClaudeProvider
from pipeline.registry import STAGES, cached_data, outline_of, write_cache

MAX_BLOCKS = 6

# 규약이 허용하는 인라인 태그. 이 밖은 전부 벗긴다(안쪽 글자는 남긴다).
_KEEP = {"b", "code", "br", "sub", "sup"}
_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")
# 표는 통째로 오므로 표 태그만 따로 허용한다.
_TABLE_KEEP = _KEEP | {"table", "thead", "tbody", "tr", "th", "td"}
_TR = re.compile(r"<tr\b", re.I)

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "data_id": {"type": "string"},
                    "title": {"type": "string"},
                    "blocks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string",
                                         "enum": ["p", "li", "table"]},
                                "html": {"type": "string"},
                            },
                            "required": ["kind", "html"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["data_id", "title", "blocks"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["slides"],
    "additionalProperties": False,
}


def clean_html(s: str, *, table: bool = False) -> str:
    """규약 밖 태그를 벗긴다. **글자는 안 지운다** — 태그만 없앤다."""
    keep = _TABLE_KEEP if table else _KEEP
    out = _TAG.sub(lambda m: m.group(0) if m.group(1).lower() in keep else "", s or "")
    # 속성은 통째로 버린다. `class`·`style` 이 붙으면 원고 CSS 밖으로 나간다.
    out = re.sub(r"<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>",
                 lambda m: f"<{m.group(1).lower()}{m.group(2)}>", out)
    return re.sub(r"\s+", " ", out).strip()


def block_lines(b: Dict[str, Any]) -> int:
    """이 블록이 화면에서 **몇 줄로 세어지는가.** 표만 행 수만큼이다."""
    return len(_TR.findall(b.get("html") or "")) or 1 if b.get("kind") == "table" else 1


def build_brief(project: Dict[str, Any], batch: List[Dict[str, Any]],
                by_page: Dict[int, str]) -> str:
    lines = [f"# 책", project.get("book") or "", f"\n# 이 장", project.get("title") or ""]
    if tone := (project.get("tone") or "").strip():
        lines += ["\n# 문체 주문", tone]
    lines.append("\n# 쓸 장")
    for s in batch:
        pages = s.get("pages") or []
        budget = int(s.get("blocks_budget") or 4)
        text = "그림" if s.get("visual") == "svg" else "표"
        lines += [
            f"\n## {s['data_id']}  ({s.get('no') or ''} {s.get('title') or ''})",
            f"- 줄 예산: {budget}줄 (그림·표 포함)",
            f"- 이 장에 붙을 것: {text} — {s.get('visual_note') or ''}",
            f"- 말할 것: {s.get('say') or ''}",
            f"- 근거 쪽: {pages}",
            "- 근거 원문:",
            "```",
            bk.pages_text(by_page, pages[0] if pages else 0,
                          pages[-1] if pages else 0) or "(원문을 못 찾았습니다)",
            "```",
        ]
    return "\n".join(lines)


def _repair(raw: Dict[str, Any], batch: List[Dict[str, Any]]) -> tuple[Dict, List[str]]:
    want = {s["data_id"]: s for s in batch}
    out: Dict[str, Dict[str, Any]] = {}
    warn: List[str] = []

    for s in raw.get("slides") or []:
        did = (s.get("data_id") or "").strip()
        # 쪼갠 장(`…-03b`)은 원래 장이 브리프에 있으면 받아 준다
        base = did.rstrip("bcdef") if did not in want else did
        if base not in want:
            warn.append(f"모르는 이름표라 버렸습니다: {did}")
            continue
        # 짐작한 예산. **자르는 근거가 아니라 견주는 값이다.**
        budget = min(int(want[base].get("blocks_budget") or 4), MAX_BLOCKS)
        svg = want[base].get("visual") == "svg"
        if svg:
            budget = max(1, budget - 1)          # 그림이 한 줄을 먹는다

        blocks: List[Dict[str, Any]] = []
        used = 0
        for b in s.get("blocks") or []:
            kind = b.get("kind") if b.get("kind") in ("p", "li", "table") else "p"
            h = clean_html(b.get("html") or "", table=(kind == "table"))
            if not h:
                continue
            # ★ 여기서 끊지 않는다. 모델이 쓴 줄은 **전부 싣는다.**
            blocks.append({"kind": kind, "html": h})
            used += block_lines({"kind": kind, "html": h})

        # 넘친 것은 **말만 한다.** 한 화면에 안 들어가면 b7 이 재서 잡고, 사람이
        # 목차 화면에서 장을 나누거나 그 장을 뺀다 — 자르는 것과 나누는 것은 다르다.
        total = used + (1 if svg else 0)
        if total > MAX_BLOCKS:
            warn.append(f"{did}: {total}줄 — 한 화면(6줄)을 넘길 수 있습니다. "
                        f"자르지 않았으니 실측을 보고 나누거나 빼세요")
        elif used > budget:
            warn.append(f"{did}: 줄 예산 {budget}인데 {used}줄 — 그대로 뒀습니다")

        if not blocks:
            warn.append(f"{did}: 몸통이 비었습니다")
            continue
        out[did] = {"data_id": did, "title": (s.get("title") or want[base]["title"]).strip(),
                    "blocks": blocks, "lines": used, "from": base}

    for did in want:
        if not any(v["from"] == did for v in out.values()):
            warn.append(f"{did}: 몸통이 안 왔습니다")
    return out, warn


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["b3-write"]
    cfg = config.load()
    src = cached_data(pid, slug, "b1-pdf") or {}
    outline = outline_of(pid, slug)
    slides = outline.get("slides") or []
    if not slides:
        raise RuntimeError("장 나누기(b2-outline)를 먼저 돌리세요")

    md = Path(src.get("md_file") or "").read_text(encoding="utf-8")
    by_page = bk.split_pages(md)
    system = (Path(__file__).resolve().parent.parent
              / "llm" / "prompts" / "write.md").read_text(encoding="utf-8")

    size = max(1, int(cfg["manuscript"]["batch"]))
    batches = [slides[i:i + size] for i in range(0, len(slides), size)]
    done: Dict[str, Dict[str, Any]] = {}
    warn: List[str] = []
    cost = 0.0

    p = ClaudeProvider(
        model=(project.get("models") or {}).get("write") or cfg["models"]["write"],
        effort=cfg["effort"]["write"],
        budget_usd=cfg["budget_usd"]["per_stage"],
    )
    for i, batch in enumerate(batches):
        job.progress(i, len(batches), f"{batch[0]['data_id']} … {batch[-1]['data_id']}")
        try:
            raw = p.structured(system,
                               [{"role": "user",
                                 "content": build_brief(project, batch, by_page)}],
                               schema=SCHEMA)
        except Exception as e:                      # noqa: BLE001
            # ★ 한 묶음이 죽어도 나머지는 살린다. 예순 장을 쓰는 도중 마흔 번째에서
            #   끊기면 앞의 서른아홉 장을 다시 쓰게 되는데, 그게 제일 비싸다.
            warn.append(f"{batch[0]['data_id']} 묶음 실패: {type(e).__name__}: {e}")
            continue
        cost += p.last_cost_usd
        part, w = _repair(raw, batch)
        done.update(part)
        warn.extend(w)
    job.progress(len(batches), len(batches), "정리")

    if not done:
        raise RuntimeError("몸통이 하나도 안 나왔습니다. 로그의 실패 이유를 보세요")

    ws.write_json(ws.step_dir(pid, slug, "draft") / "draft.json", {"slides": done})
    total = sum(v["lines"] for v in done.values())
    job.add_log(f"{len(done)}장 · 줄 {total}개 (장당 평균 {total / len(done):.1f}) "
                f"· ${cost:.3f}")
    for w in warn[:10]:
        job.add_log(w)

    return write_cache(pid, slug, "b3-write",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"slides": done, "lines": total},
                       code_version=stage.code_version,
                       model=p.model, cost_usd=cost,
                       status="degraded" if warn else "ok", warnings=warn)


STAGES["b3-write"].run = run
