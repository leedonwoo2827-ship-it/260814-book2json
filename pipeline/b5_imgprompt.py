# -*- coding: utf-8 -*-
"""B5 이미지 프롬프트 — **원장에 없는 장만 만든다.**

이 단계의 핵심은 안 부르는 것이다. 원장(`core/ledger.py`)에 이름표가 있고 몸통
해시가 같으면 Claude 를 안 부르고 옛 프롬프트를 그대로 쓴다. 값을 아끼려는 게
아니라, **같은 장의 프롬프트가 이유 없이 바뀌면 이미 그려 둔 그림과 어긋나기**
때문이다.

★ 문체(`style_hint`)와 「글자 없음」 꼬리는 **코드가 붙인다.** 모델이 매번 다시
  쓰게 두면 장마다 조금씩 달라져서 한 덱 안에서 그림 결이 갈린다. 참고로 받은
  샘플(`_contex/…이미지프롬프트 (1).json`)도 34개 프롬프트에 같은 문구가 그대로
  박혀 있다 — 그 앱이 첫 40자로 중복을 거르므로 두 번 들어가지도 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core import config, ledger as lg, workspace as ws
from llm.claude_provider import ClaudeProvider
from pipeline.registry import STAGES, cached_data, outline_of, write_cache

BATCH = 10
LEVELS = ("기억", "이해", "적용", "분석", "평가", "창조")

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "data_id": {"type": "string"},
                    "title": {"type": "string"},
                    "level": {"type": "string", "enum": list(LEVELS)},
                    "prompt": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["data_id", "title", "level", "prompt", "keywords"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["prompts"],
    "additionalProperties": False,
}


def style_hint(cfg: Dict[str, Any]) -> str:
    """모든 프롬프트에 공통으로 붙는 문체 한 줄.

    ★ 받은 샘플은 `square 1:1 composition … center-cropped` 로 끝난다. 그것을
      그대로 두고 `aspect` 만 `landscape` 로 바꾸면 **가로 캔버스 한가운데
      정사각형 그림이 앉고 좌우가 빈다.** 문구가 곧 구도라, 여기를 다시 썼다.
      샘플이 square 였던 이유는 그쪽 앱의 사진 자리가 세로 패널이어서였고
      (`260804-ppt2eduvideo/core/deck_builder.py:1679`), 우리는 반대다.
    """
    img = cfg["image"]
    return ("clean modern educational illustration, flat vector with subtle depth, "
            "consistent line weight, no gradient mesh, "
            f"deep teal ({img['accent_a']}) and warm sand ({img['accent_b']}) accents, "
            "generous negative space, uncluttered, "
            "wide horizontal 3:2 composition with the subject spread across the full "
            "width and safe margins on the left and right "
            "(the image may be cropped to 16:9 for video)")


def compose(body: str, cfg: Dict[str, Any]) -> str:
    """모델이 쓴 장면 묘사 + 공통 문체 + 「글자 없음」 꼬리.

    글자 없음을 **세 겹**으로 건다: 묘사 끝의 `no text.` · 아래 꼬리 · 그리고
    `negative` 칸(이미지 스튜디오가 `Avoid: …` 로 붙여 준다). 샘플과 같은 방식이다
    — 한 겹만 걸면 모델이 곧잘 글자를 그린다.
    """
    s = (body or "").strip().rstrip(".")
    if "no text" not in s.lower():
        s += ", no text"
    return f"{s}. {style_hint(cfg)}. No text, no watermark, no logo."


def build_brief(project: Dict[str, Any], batch: List[Dict[str, Any]]) -> str:
    lines = [f"# 책", project.get("book") or "", f"\n# 이 장", project.get("title") or "",
             "\n# 그림을 붙일 장"]
    for s in batch:
        rows = "\n".join(f"  - {b['html']}" for b in (s.get("blocks") or []))
        lines += [
            f"\n## {s['data_id']}  {s.get('title') or ''}",
            f"- 말할 것: {s.get('say') or ''}",
            "- 화면 문구:",
            rows or "  (없음)",
        ]
    return "\n".join(lines)


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["b5-imgprompt"]
    cfg = config.load()
    draft = (cached_data(pid, slug, "b3-write") or {}).get("slides") or {}
    if not draft:
        raise RuntimeError("몸통 쓰기(b3-write)를 먼저 돌리세요")

    by_id = {s["data_id"]: s for s in (outline_of(pid, slug).get("slides") or [])}
    slides: List[Dict[str, Any]] = []
    for did, body in draft.items():
        base = by_id.get(did) or by_id.get(body.get("from") or "") or {}
        slides.append({
            "data_id": did,
            "title": body.get("title") or base.get("title") or "",
            "say": base.get("say") or "",
            "blocks": body.get("blocks") or [],
            "body_hash": lg.body_hash(body.get("blocks") or [], body.get("title") or ""),
        })

    book = ws.load_ledger(pid, slug)
    make_ids, keep_ids = lg.plan(book, slides)
    if force:
        make_ids, keep_ids = [s["data_id"] for s in slides], []
    job.add_log(f"새로 쓸 장 {len(make_ids)}개 · 원장에서 그대로 {len(keep_ids)}개")

    made: Dict[str, Dict[str, Any]] = {}
    warn: List[str] = []
    cost = 0.0

    if make_ids:
        want = [s for s in slides if s["data_id"] in set(make_ids)]
        system = (Path(__file__).resolve().parent.parent
                  / "llm" / "prompts" / "imgprompt.md").read_text(encoding="utf-8")
        batches = [want[i:i + BATCH] for i in range(0, len(want), BATCH)]
        p = ClaudeProvider(
            model=(project.get("models") or {}).get("imgprompt") or cfg["models"]["imgprompt"],
            effort=cfg["effort"]["imgprompt"],
            budget_usd=cfg["budget_usd"]["per_stage"],
        )
        for i, batch in enumerate(batches):
            job.progress(i, len(batches), f"{batch[0]['data_id']} … {batch[-1]['data_id']}")
            try:
                raw = p.structured(system,
                                   [{"role": "user",
                                     "content": build_brief(project, batch)}],
                                   schema=SCHEMA)
            except Exception as e:                    # noqa: BLE001
                warn.append(f"{batch[0]['data_id']} 묶음 실패: {type(e).__name__}: {e}")
                continue
            cost += p.last_cost_usd
            for r in raw.get("prompts") or []:
                did = (r.get("data_id") or "").strip()
                if did not in draft:
                    warn.append(f"모르는 이름표라 버렸습니다: {did}")
                    continue
                body = (r.get("prompt") or "").strip()
                if len(body) < 40:
                    warn.append(f"{did}: 장면 묘사가 너무 짧습니다")
                    continue
                made[did] = {
                    "title": (r.get("title") or "").strip(),
                    "level": r.get("level") if r.get("level") in LEVELS else "이해",
                    # ★ 샘플 JSON 은 전부 `photo` 다. 이 앱은 그림을 깔기만 하므로
                    #   갈릴 축이 없어 고정한다 — 이미지 스튜디오도 이 칸을 안 읽는다.
                    "type": "photo",
                    "prompt": compose(body, cfg),
                    "keywords": [str(k) for k in (r.get("keywords") or [])][:1],
                }
        job.progress(len(batches), len(batches), "정리")

    book = lg.apply(book, made, slides)
    ws.save_ledger(pid, slug, book)

    miss = [s["data_id"] for s in slides
            if not ((book["by_id"].get(s["data_id"]) or {}).get("prompt") or "").strip()]
    job.add_log(f"원장 {len(book['by_id'])}칸 · 프롬프트 있는 장 {len(slides) - len(miss)}"
                f"/{len(slides)}개 · ${cost:.3f}")
    if miss:
        job.add_log(f"프롬프트가 없는 장 {len(miss)}개: {', '.join(miss[:10])}")
    for w in warn[:10]:
        job.add_log(w)

    return write_cache(pid, slug, "b5-imgprompt",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"made": len(made), "kept": len(keep_ids),
                             "missing": miss, "ledger": len(book["by_id"])},
                       code_version=stage.code_version,
                       cost_usd=cost,
                       status="degraded" if miss or warn else "ok",
                       warnings=warn + ([f"프롬프트가 없는 장 {len(miss)}개"] if miss else []))


STAGES["b5-imgprompt"].run = run
