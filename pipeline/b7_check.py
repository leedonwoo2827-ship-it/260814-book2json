# -*- coding: utf-8 -*-
"""B7 실측 검증 — **이 앱의 값어치가 여기 있다.**

규약을 지켰는지 말로 확인하지 않는다. 원고를 진짜 브라우저에 띄우고 장마다
높이를 잰다. 규약의 숫자가 전부 픽셀이라, 재지 않은 「지켰습니다」는 믿을 것이
못 된다.

여기서 안 잡으면 발표 쇼케이스가 받아서 조용히 이상해진다 — 넘친 장은 그 장만
축소되어 장을 넘길 때마다 글자 크기가 튀고, 빈 장은 제목만 덩그러니 남는다.
저쪽에서 알게 되면 이미 늦다.

★ Claude 를 안 부른다. 돈이 안 들고, 몇 번을 돌려도 된다.
★ playwright 가 없으면 **멈추지 않고 건너뛴다.** 잴 수 없다는 것과 어긋났다는
  것은 다른 말이다 — `status="skipped"` 로 남겨서 화면이 그 차이를 보여 준다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from core import config, narration as nr, workspace as ws
from pipeline.registry import STAGES, cached_data, write_cache

APP = Path(__file__).resolve().parent.parent
SCRIPT = APP / "tools" / "measure.mjs"
TIMEOUT = 180

# 어긋남의 종류 → 사람에게 할 말. **무엇을 하라고**까지 적는다.
#
# ★ `bare`(그림도 표도 없음)가 여기 있었다. 뺐다(2026-08-14 지적) — 그것은 **규약을
#   어긴 것이 아니라 아직 안 그린 것**이다. 그림 단계(b4)를 안 돌린 원고를 재면
#   스물한 장이 통째로 「규약에 어긋난 장」으로 뜨는데, 진짜로 어긋난 장(한 화면을
#   넘친 장)이 그 사이에 묻힌다. 목록이 길면 목록을 안 읽게 된다.
#   그림이 없는 장 수는 아래에서 **숫자로만** 말한다.
WHY = {
    "over": ("한 화면을 넘쳤습니다", "h3 를 하나 더 만들어 나누세요 (내용은 그대로)"),
    "longer": ("줄이 너무 많습니다", "여섯 줄 안쪽으로 줄이거나 장을 나누세요"),
    "empty": ("몸통이 없습니다", "b3-write 를 다시 돌리세요"),
}


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["b7-check"]
    cfg = config.load()["manuscript"]
    built = cached_data(pid, slug, "b6-assemble") or {}
    path = Path(built.get("file") or "")
    if not path.is_file():
        raise RuntimeError("원고 조립(b6-assemble)을 먼저 돌리세요")

    node = shutil.which("node")
    if not node or not SCRIPT.is_file():
        job.add_log("node 나 measure.mjs 가 없어 실측을 건너뜁니다")
        job.add_log("setup.bat 을 다시 돌리면 playwright 가 깔립니다")
        return write_cache(pid, slug, "b7-check",
                           input_hash=stage.input_hash(pid, slug, project),
                           data={"measured": False, "slides": 0, "violations": []},
                           code_version=stage.code_version, status="skipped",
                           warnings=["실측하지 못했습니다 — 규약을 어겼는지 모릅니다"])

    job.progress(0, 1, "브라우저에 띄워 재는 중")
    cmd = [node, str(SCRIPT), str(path),
           "--width", str(int(cfg["box_w"]) + 16),      # UA body margin 8px × 2
           "--box", str(cfg["box_h"]),
           "--max-blocks", str(cfg["max_blocks"])]
    try:
        r = subprocess.run(cmd, cwd=str(APP), capture_output=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"실측이 {TIMEOUT}초 안에 안 끝났습니다") from None
    if r.returncode != 0:
        tail = (r.stderr or b"").decode("utf-8", "replace").strip()[-400:]
        raise RuntimeError(f"실측이 실패했습니다 ({r.returncode})\n{tail}")

    try:
        report = json.loads((r.stdout or b"").decode("utf-8"))
    except json.JSONDecodeError:
        raise RuntimeError("실측 결과를 못 읽었습니다") from None

    slides: List[Dict[str, Any]] = report.get("slides") or []
    bad: List[Dict[str, Any]] = []
    for s in slides:
        flags = [k for k in WHY if s.get(k)]
        if flags:
            bad.append({"id": s.get("id") or "", "title": s.get("title") or "",
                        "height": s.get("height"), "lines": s.get("lines"),
                        "flags": flags})

    heights = [s.get("height") or 0 for s in slides] or [0]
    n_say = sum(1 for s in slides if s.get("say"))
    n_img = sum(1 for s in slides if s.get("img"))
    n_svg = sum(1 for s in slides if s.get("svg"))
    n_tab = sum(1 for s in slides if s.get("table"))
    lines = sum(s.get("lines") or 0 for s in slides)

    # 실측은 **되짚을 때만** 보는 값이라 넘기는 칸에 두지 않는다 — `bak/` 으로.
    ws.write_json(ws.step_dir(pid, slug, "export") / "bak" / "실측.json", report)

    # 규약 편지의 「붙임」과 같은 꼴로 찍는다 — 사람이 그 편지와 나란히 읽는다.
    job.add_log(f"{len(slides)}장 · 줄 {lines}개 "
                f"(장당 최소 {min(s.get('lines') or 0 for s in slides) if slides else 0} · "
                f"평균 {lines / max(1, len(slides)):.1f} · "
                f"최대 {max((s.get('lines') or 0) for s in slides) if slides else 0})")
    job.add_log(f"높이 최대 {max(heights)}px / {cfg['box_h']}px · "
                f"한 화면을 넘친 장 {sum(1 for s in slides if s.get('over'))}개")
    # 그림이 없는 장은 **숫자로만.** 「어긋난 장」이 아니라 「아직 안 그린 장」이다.
    n_bare = sum(1 for s in slides if s.get("bare"))
    job.add_log(f"그림 {n_svg}장 · 표 {n_tab}장"
                + (f" · 아직 그림이 없는 장 {n_bare}개 (3번의 그림 단계)" if n_bare else ""))
    # ★ 실측이 재는 것은 픽셀만이 아니다. **대본 글자 수가 곧 영상 길이**라,
    #   원고에 실제로 박힌 `data-say` 를 여기서 세어 몇 분짜리인지 말한다.
    said = (sum(int(s.get("say") or 0) for s in slides)
            + int(report.get("intro") or 0) + int(report.get("outro") or 0))
    want = nr.plan_of(project, int((cached_data(pid, slug, "b1-pdf") or {}).get("chars") or 0))
    length = nr.verdict(said, want)
    job.add_log(f"data-say {n_say}/{len(slides)} · data-img {n_img}/{len(slides)}")
    job.add_log(f"대본 {said:,}자 → {length['clock']} "
                f"(목표 {want['minutes']}분 · {length['pct']}%)")
    thin = [s for s in slides
            if int(s.get("say") or 0) < want["say_per_slide"] * 0.6]
    if thin:
        job.add_log(f"말이 짧은 장 {len(thin)}개: "
                    + ", ".join(f"{s.get('id')}({s.get('say')}자)" for s in thin[:8]))

    warn: List[str] = []
    if length["short"]:
        warn.append(length["note"])
    if report.get("wide"):
        warn.append("가로로 밀렸습니다 — 표나 그림이 944px 을 넘습니다")
        job.add_log(warn[-1])
    for b in bad[:12]:
        what, fix = WHY[b["flags"][0]]
        job.add_log(f"{b['id']} {b['title'][:28]} — {what} "
                    f"({b['height']}px · {b['lines']}줄) → {fix}")
    if len(bad) > 12:
        job.add_log(f"… 그 밖에 {len(bad) - 12}개. 실측.json 에 전부 있습니다")
    if bad:
        warn.append(f"규약에 어긋난 장 {len(bad)}개")
    else:
        job.add_log("규약에 어긋난 장 없음 — 그대로 발표 쇼케이스에 넣어도 됩니다")

    return write_cache(pid, slug, "b7-check",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"measured": True, "slides": len(slides), "lines": lines,
                             "max_height": max(heights), "violations": bad,
                             "wide": bool(report.get("wide")),
                             "svg": n_svg, "table": n_tab,
                             "say": n_say, "img": n_img, "length": length},
                       code_version=stage.code_version,
                       status="degraded" if warn else "ok", warnings=warn)


STAGES["b7-check"].run = run
