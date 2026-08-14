# -*- coding: utf-8 -*-
"""B4 그림 — **장마다 하나씩. 선택이 아니다.**

「줄글만이 아닌 게 목표」라 이 단계가 빠지면 원고가 목적을 잃는다. 표가 있는 장은
표가 그 역할을 하므로 건너뛰고, 나머지는 전부 SVG 를 받는다.

★ 그림은 **여섯 장씩** 묶어 부른다. SVG 는 출력이 길어서(한 장에 700~1,500자)
  여덟 장을 묶으면 뒤쪽 그림의 좌표가 뭉개진다 — 상자가 겹치거나 viewBox 를
  벗어난다. b3 보다 묶음을 작게 두는 이유가 이것이다.

★ 나온 SVG 는 **파싱해서 검사한다.** 뚫린 태그, 바깥 파일 참조, 세로로 긴 viewBox
  는 여기서 버린다. 원고에 들어간 뒤에는 브라우저가 조용히 삼켜서, 사람이 발표
  중에야 그림이 없다는 것을 안다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from core import config, workspace as ws
from llm.claude_provider import ClaudeProvider
from pipeline.registry import STAGES, cached_data, outline_of, write_cache

BATCH = 6
# 원고 CSS 는 `svg{max-height:240px; width:auto}` 다. 세로로 긴 그림은 **잘리는 게
# 아니라 통째로 작아진다** — 높이 240 에 맞춰 줄면서 폭도 같이 줄어, 944px 짜리 판
# 한가운데 손바닥만 한 그림이 앉고 글자는 못 읽는다. 그래서 비율에서 막는다.
# 520×220 이 0.42 다. 0.55 는 520×286 — 여기부터 눈에 띄게 작아진다.
MAX_H_RATIO = 0.55

_ALLOWED = {"svg", "g", "defs", "marker", "rect", "circle", "ellipse", "line",
            "polyline", "polygon", "path", "text", "tspan", "title", "desc"}
_EXTERNAL = re.compile(r"<image\b|@import|url\s*\(\s*['\"]?https?:|<style\b", re.I)
_VIEWBOX = re.compile(r'viewBox\s*=\s*"([-\d.\s]+)"')

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "figures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "data_id": {"type": "string"},
                    "svg": {"type": "string"},
                },
                "required": ["data_id", "svg"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["figures"],
    "additionalProperties": False,
}


def check_svg(svg: str) -> tuple[Optional[str], str]:
    """(쓸 수 있는 SVG, 못 쓰는 이유). 둘 중 하나는 빈 값이다."""
    s = (svg or "").strip()
    if not s.startswith("<svg"):
        return None, "svg 태그로 시작하지 않습니다"
    if _EXTERNAL.search(s):
        return None, "바깥 파일이나 style 블록을 씁니다"

    m = _VIEWBOX.search(s)
    if not m:
        return None, "viewBox 가 없습니다"
    try:
        _, _, w, h = (float(x) for x in m.group(1).split())
    except ValueError:
        return None, f"viewBox 를 못 읽었습니다: {m.group(1)}"
    if w <= 0 or h <= 0:
        return None, "viewBox 의 크기가 0 입니다"
    if h / w > MAX_H_RATIO:
        return None, f"세로로 깁니다 ({w:.0f}×{h:.0f}) — 가로로 긴 꼴이어야 합니다"

    # ★ 진짜 파서를 쓴다. 정규식으로 뚫린 태그를 잡으려다 놓치면 원고 전체의
    #   HTML 이 그 지점부터 무너진다(닫히지 않은 <g> 가 뒤 내용을 통째로 삼킨다).
    try:
        root = ET.fromstring(s)
    except ET.ParseError as e:
        return None, f"XML 이 깨졌습니다: {e}"

    bad = {t.rsplit("}", 1)[-1] for t in (e.tag for e in root.iter())} - _ALLOWED
    if bad:
        return None, "쓸 수 없는 요소: " + ", ".join(sorted(bad))

    # `<svg width height>` 가 박혀 있으면 폭에 맞춰 늘어나지 않는다 — 지우고 쓴다.
    # ★ **여는 `<svg>` 태그 안에서만** 지운다. 예전에 문자열 전체에서 앞의 두 개를
    #   지웠더니, 루트에 width·height 가 없는(=규약을 잘 지킨) 그림에서 **첫
    #   `<rect>` 의 width·height 가 대신 날아갔다.** 크기 없는 사각형은 안 그려지고,
    #   XML 도 멀쩡해서 검사에 안 걸린다 — 발표 화면에서야 빈 자리로 보인다.
    head_end = s.index(">")
    head = re.sub(r'\s(width|height)\s*=\s*"[^"]*"', "", s[:head_end])
    return head + s[head_end:], ""


def build_brief(project: Dict[str, Any], batch: List[Dict[str, Any]],
                draft: Dict[str, Any]) -> str:
    lines = [f"# 책", project.get("book") or "", f"\n# 이 장", project.get("title") or "",
             "\n# 그릴 장"]
    for s in batch:
        body = draft.get(s["data_id"]) or {}
        rows = "\n".join(f"  - {b['html']}" for b in (body.get("blocks") or []))
        lines += [
            f"\n## {s['data_id']}  ({s.get('no') or ''} {s.get('title') or ''})",
            f"- 그릴 것: {s.get('visual_note') or ''}",
            f"- 말할 것: {s.get('say') or ''}",
            "- 이 장의 화면 문구(그림은 이것과 같은 것을 말해야 한다):",
            rows or "  (없음)",
        ]
    return "\n".join(lines)


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["b4-figure"]
    cfg = config.load()
    outline = outline_of(pid, slug)
    draft = (cached_data(pid, slug, "b3-write") or {}).get("slides") or {}
    if not draft:
        raise RuntimeError("몸통 쓰기(b3-write)를 먼저 돌리세요")

    # ★ 대상은 **원고에 실제로 있는 장**이다. b3 가 장을 쪼갰으면(`…-03b`) 그 장도
    #   그림이 필요하다 — 목차만 보면 쪼갠 장이 통째로 그림 없이 나간다.
    #
    # ★ 거르는 기준은 목차가 뭐라고 했는가(`visual`)가 **아니라** 몸통에 표가
    #   실제로 있는가다. 예전엔 목차가 `table` 이라 한 장을 건너뛰었는데, b3 가
    #   그 장을 표 없이 줄글로 써 오면 **아무도 안 그린다.** 20장의 `sam20-19` 가
    #   그렇게 그림도 표도 없이 나갔고, b6·b7 이 잡아 줬는데도 b4 를 다시 눌러
    #   봐야 "새로 그릴 장이 없습니다" 만 나왔다 — 고칠 방법이 없는 경고였다.
    #   목차는 의도이고 원고는 사실이다. **사실을 본다.**
    by_id = {s["data_id"]: s for s in (outline.get("slides") or [])}
    targets: List[Dict[str, Any]] = []
    for did, body in draft.items():
        base = by_id.get(did) or by_id.get(body.get("from") or "") or {}
        if any(b["kind"] == "table" for b in body.get("blocks") or []):
            continue                                  # 표가 이미 그 자리를 맡았다
        targets.append({**base, "data_id": did,
                        "title": body.get("title") or base.get("title") or ""})

    if not targets:
        job.add_log("그림이 필요한 장이 없습니다 — 전부 표로 갑니다")
        return write_cache(pid, slug, "b4-figure",
                           input_hash=stage.input_hash(pid, slug, project),
                           data={"figures": {}}, code_version=stage.code_version,
                           status="skipped")

    # ★ 이미 그린 것은 **다시 안 그린다.** 그림은 한 묶음이 통째로 실패하는 일이
    #   잦아서(좌표가 어긋나 검사에 걸린다), 다시 눌러 남은 것만 채우는 흐름이
    #   실제 사용법이다. 그때 멀쩡한 그림까지 새로 그리면 값도 값이지만 **이미
    #   눈으로 확인한 그림이 다른 것으로 바뀐다** — 그게 더 나쁘다.
    all_targets = targets
    figures: Dict[str, str] = {} if force else \
        dict((cached_data(pid, slug, "b4-figure") or {}).get("figures") or {})
    # 원고에서 사라진 장의 그림은 들고 있어 봐야 조립에서 안 쓰인다
    figures = {k: v for k, v in figures.items() if k in draft}
    kept = sum(1 for t in targets if t["data_id"] in figures)
    targets = [t for t in targets if t["data_id"] not in figures]
    if kept:
        job.add_log(f"이미 그린 {kept}개는 그대로 둡니다")
    if not targets:
        job.add_log("새로 그릴 장이 없습니다")
        return write_cache(pid, slug, "b4-figure",
                           input_hash=stage.input_hash(pid, slug, project),
                           data={"figures": figures, "missing": []},
                           code_version=stage.code_version, status="ok")

    system = (Path(__file__).resolve().parent.parent
              / "llm" / "prompts" / "figure.md").read_text(encoding="utf-8")
    batches = [targets[i:i + BATCH] for i in range(0, len(targets), BATCH)]
    warn: List[str] = []
    cost = 0.0

    p = ClaudeProvider(
        model=(project.get("models") or {}).get("figure") or cfg["models"]["figure"],
        effort=cfg["effort"]["figure"],
        budget_usd=cfg["budget_usd"]["per_stage"],
    )
    for i, batch in enumerate(batches):
        job.progress(i, len(batches), f"{batch[0]['data_id']} … {batch[-1]['data_id']}")
        try:
            raw = p.structured(system,
                               [{"role": "user",
                                 "content": build_brief(project, batch, draft)}],
                               schema=SCHEMA)
        except Exception as e:                        # noqa: BLE001
            warn.append(f"{batch[0]['data_id']} 묶음 실패: {type(e).__name__}: {e}")
            continue
        cost += p.last_cost_usd
        for f in raw.get("figures") or []:
            did = (f.get("data_id") or "").strip()
            if did not in draft:
                warn.append(f"모르는 이름표라 버렸습니다: {did}")
                continue
            ok, why = check_svg(f.get("svg") or "")
            if ok:
                figures[did] = ok
            else:
                warn.append(f"{did}: {why}")
    job.progress(len(batches), len(batches), "정리")

    missing = [t["data_id"] for t in all_targets if t["data_id"] not in figures]
    ws.write_json(ws.step_dir(pid, slug, "figure") / "figures.json",
                  {"figures": figures, "missing": missing})

    job.add_log(f"그림이 필요한 장 {len(all_targets)}개 → 있는 것 {len(figures)}개 "
                f"(이번에 새로 {len(figures) - kept}개) · ${cost:.3f}")
    if missing:
        job.add_log(f"그림 없이 남은 장 {len(missing)}개: {', '.join(missing[:10])}")
        job.add_log("이 단계를 다시 돌리면 남은 장만 새로 그립니다")
    for w in warn[:10]:
        job.add_log(w)

    return write_cache(pid, slug, "b4-figure",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"figures": figures, "missing": missing},
                       code_version=stage.code_version,
                       model=p.model, cost_usd=cost,
                       status="degraded" if missing or warn else "ok",
                       warnings=warn + ([f"그림이 없는 장 {len(missing)}개"] if missing else []))


STAGES["b4-figure"].run = run
