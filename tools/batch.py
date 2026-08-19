# -*- coding: utf-8 -*-
"""여러 장을 한꺼번에 원고화한다 — **밤에 걸어 두고 아침에 받는 자리.**

    python tools/batch.py "_contex/새뮤얼슨의경제학-5부 22장.pdf" ... [--min 15]

한 장에 35~40분 · 약 $6 이 든다. 열 장이면 여섯 시간 · $60 이다. 그래서 이 스크립트는
**세 가지를 지킨다.**

1. **이어서 돌린다.** 이미 끝난 단계는 건너뛴다(캐시가 fresh 면 그대로 쓴다).
   중간에 끊겨도 다시 실행하면 끊긴 자리에서 이어진다 — 여섯 시간짜리 작업에서
   처음부터 다시 하는 것은 못 할 짓이다.
2. **한 장이 실패해도 멈추지 않는다.** 그 장만 기록에 남기고 다음 장으로 간다.
   열 장 중 하나가 API 오류로 죽었다고 나머지 아홉을 못 만들 이유가 없다.
3. **다 끝나면 표로 말한다.** 장마다 몇 장·몇 분·어긋난 장 몇 개·얼마 썼는지.
   사람이 확인할 자리가 사라지는 것이 일괄 실행의 값이라, 그 대가를 목록으로 돌려준다.

★ **서버를 끄고 돌려라.** 서버는 한 번에 한 잡만 돌리는데(core/jobs.py), 이 스크립트는
  그 registry 를 안 거치고 스테이지를 직접 부른다. 같은 프로젝트를 양쪽에서 만지면
  캐시가 어긋난다. 새 프로젝트만 만드므로 사고가 날 자리는 좁지만, 껴 두는 편이 맞다.
"""
from __future__ import annotations

import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline  # noqa: F401  — import 만으로 여섯 단계가 붙는다
from core import narration as nr, workspace as ws
from pipeline.registry import ORDER, STAGES, cached_data, read_cache


class Log:
    """스테이지가 기대하는 `job` 자리. 화면과 파일에 같이 적는다."""

    def __init__(self, path: Path) -> None:
        self.f = path.open("a", encoding="utf-8")
        self.last = ""

    def say(self, line: str) -> None:
        print(line, flush=True)
        self.f.write(line + "\n")
        self.f.flush()

    # ── 스테이지가 부르는 것 둘 ──
    def add_log(self, line: str) -> None:
        self.say("      " + line)

    def progress(self, completed: int, total: int, step: str = "") -> None:
        # 같은 말을 반복해서 찍지 않는다 — 여섯 시간짜리 로그가 읽을 수 없게 된다.
        if step and step != self.last:
            self.last = step
            self.say(f"      … {step}")


def guess(name: str) -> Dict[str, str]:
    """파일 이름에서 책·장·이름표. 서버의 새 원고 화면과 같은 규칙이다."""
    stem = re.sub(r"\.pdf$", "", name, flags=re.I).strip()
    parts = [x.strip() for x in stem.split("-") if x.strip()]
    book = parts[0] if len(parts) > 1 else ""
    ch = (re.search(r"(\d+)\s*장", stem) or [None, ""])[1]
    return {"book": book, "title": f"제{ch}장" if ch else stem,
            "prefix": f"ch{ch}" if ch else "bk"}


def find_project(pdf: Path) -> Dict[str, Any] | None:
    """같은 PDF 로 이미 만든 프로젝트가 있으면 그것을 쓴다(이어서 돌리기)."""
    for p in ws.list_projects():
        doc = ws.load_project(p["id"], p["slug"])
        if any(Path(x).name == pdf.name for x in doc.get("pdfs") or []):
            doc.setdefault("slug", p["slug"])
            return doc
    return None


def make_project(pdf: Path, minutes: int) -> Dict[str, Any]:
    g = guess(pdf.name)
    pid = ws.next_pid()
    slug = ws.slug(g["title"])
    doc = {
        "id": pid, "slug": slug, "title": g["title"], "book": g["book"],
        "pdfs": [str(pdf)], "id_prefix": g["prefix"],
        "target_min": minutes,
        "slide_budget": 0,              # 0 = 목차가 원문을 보고 정한다
        "drop_head": 2, "drop_tail": 0, # 속표지 두 쪽 — 19~21장이 다 그랬다
        "tone": "", "outline_rev": 0, "created_at": ws._now(),
    }
    ws.save_project(pid, slug, doc)
    return doc


def run_one(doc: Dict[str, Any], log: Log, *, retries: int = 1) -> Dict[str, Any]:
    """한 장을 끝까지. 이미 fresh 인 단계는 건너뛴다."""
    pid, slug = doc["id"], doc["slug"]
    spent = 0.0
    for key in ORDER:
        spec = STAGES[key]
        env = read_cache(pid, slug, key)
        want = spec.input_hash(pid, slug, doc)
        if env and env.get("input_hash") == want and env.get("status") != "skipped":
            log.say(f"   {key:<12} 그대로 씀 (${env.get('cost_usd', 0):.2f})")
            spent += env.get("cost_usd") or 0.0
            continue

        for attempt in range(retries + 1):
            t0 = time.time()
            log.say(f"   {key:<12} 시작" + (f" (다시 {attempt})" if attempt else ""))
            try:
                out = spec.run(log, pid, slug, doc, force=False)
                cost = (out or {}).get("cost_usd") or 0.0
                spent += cost
                log.say(f"   {key:<12} 끝 · {time.time() - t0:.0f}초 · ${cost:.2f}")
                break
            except Exception as e:                      # noqa: BLE001
                log.say(f"   {key:<12} 실패: {type(e).__name__}: {e}")
                if attempt >= retries:
                    raise
                time.sleep(20)
        # 프로젝트 문서를 다시 읽는다 — 스테이지가 되써 넣는 값(outline_rev)이 있다
        doc = {**ws.load_project(pid, slug), "slug": slug}

    b6 = cached_data(pid, slug, "b6-assemble") or {}
    b7 = cached_data(pid, slug, "b7-check") or {}
    ln = b6.get("length") or {}
    return {
        "id": pid, "title": doc.get("title"), "file": b6.get("file"),
        "slides": b6.get("slides"), "clock": ln.get("clock"), "pct": ln.get("pct"),
        "bad": len(b7.get("violations") or []), "cost": round(spent, 2),
    }


def main(argv: List[str]) -> int:
    minutes = nr.DEFAULT_MIN
    if "--min" in argv:
        i = argv.index("--min")
        minutes = int(argv[i + 1])
        del argv[i:i + 2]
    pdfs = [Path(x.strip().strip('"')) for x in argv]
    bad = [p for p in pdfs if not p.is_file()]
    if not pdfs or bad:
        print(f"읽을 PDF 를 못 찾았습니다: {bad or '(없음)'}")
        return 2

    stamp = time.strftime("%m%d-%H%M")
    log = Log(ws.ROOT / f"_일괄-{stamp}.log")
    log.say(f"■ {len(pdfs)}장 · 목표 {minutes}분 · 한 장에 35~40분 · 약 ${len(pdfs) * 6}")
    log.say(f"  기록: {log.f.name}\n")

    done: List[Dict[str, Any]] = []
    failed: List[str] = []
    t0 = time.time()
    for i, pdf in enumerate(pdfs, start=1):
        doc = find_project(pdf) or make_project(pdf, minutes)
        # 목표 길이는 **부른 사람이 정한다** — 예전에 만든 프로젝트라도 맞춘다
        if doc.get("target_min") != minutes:
            doc["target_min"] = minutes
            ws.save_project(doc["id"], doc["slug"], doc)
        log.say(f"[{i}/{len(pdfs)}] {doc['title']} — {pdf.name}")
        try:
            r = run_one(doc, log)
            done.append(r)
            log.say(f"   ▶ {r['slides']}장 · {r['clock']} (목표의 {r['pct']}%) · "
                    f"어긋난 장 {r['bad']}개 · ${r['cost']:.2f}")
            log.say(f"   ▶ {r['file']}\n")
        except Exception:                               # noqa: BLE001
            failed.append(doc["title"])
            log.say("   ▶ 이 장은 실패했습니다. 다음 장으로 갑니다.")
            log.say(traceback.format_exc(limit=3) + "\n")

    log.say("■ 끝났습니다 — " + f"{(time.time() - t0) / 60:.0f}분 · "
            f"${sum(r['cost'] for r in done):.2f}")
    log.say(f"{'장':<10}{'슬라이드':>8}{'길이':>12}{'목표%':>7}{'어긋남':>7}{'값':>8}")
    for r in done:
        log.say(f"{r['title']:<10}{r['slides']:>8}{r['clock']:>12}"
                f"{r['pct']:>6}%{r['bad']:>7}{'$' + format(r['cost'], '.2f'):>8}")
    for t in failed:
        log.say(f"{t:<10}  실패 — 다시 돌리면 끊긴 자리에서 이어집니다")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
