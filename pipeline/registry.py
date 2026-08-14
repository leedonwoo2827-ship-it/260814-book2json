# -*- coding: utf-8 -*-
"""스테이지 레지스트리 — DAG · 입력 해시 · 캐시 · resume.

**재실행 가능성이 이 파일의 존재 이유다.** Claude 호출은 비싸다. 한 스테이지를
다시 돌린다고 앞뒤가 같이 돌면 안 되고, 프롬프트를 고쳤을 때는 정확히 그
스테이지와 하위만 stale 이 되어야 한다.

캐시 봉투는 스테이지마다 같다:

    { "stage": "b2-outline", "code_version": 3, "input_hash": "sha256:…",
      "model": "claude-opus-5", "cost_usd": 0.184,
      "status": "ok|degraded|skipped", "warnings": [], "data": {…} }

`input_hash` = (상위 스테이지 data + 읽는 project.json 서브셋 + **프롬프트 파일
원문** + code_version) 의 canonical JSON sha256. 프롬프트를 고치면 그 스테이지가
stale 이 된다 — 코드를 안 고쳤어도.

★ 규칙: **Claude 스테이지는 stale 이어도 자동 실행하지 않는다.** 돈은 명시적
  클릭에만 쓴다. 결정론 스테이지(ffmpeg·gh·조립·렌더)만 자동 실행 대상이다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core import workspace as ws

PROMPTS = Path(__file__).resolve().parent.parent / "llm" / "prompts"


# ── 캐시 ───────────────────────────────────────────────────────────────────
def cache_path(pid: int, slug: str, stage: str) -> Path:
    return ws.cache_dir(pid, slug) / f"{stage}.json"


def read_cache(pid: int, slug: str, stage: str) -> Optional[Dict[str, Any]]:
    return ws.read_json(cache_path(pid, slug, stage), None)


def write_cache(pid: int, slug: str, stage: str, *, input_hash: str, data: Any,
                code_version: int, model: str = "", cost_usd: float = 0.0,
                status: str = "ok", warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    env = {
        "stage": stage,
        "code_version": int(code_version),
        "input_hash": input_hash,
        # ★ 언제 돌았는가. 파일 시각(mtime)으로도 알 수 있지만 복사·백업 한 번에
        #   흐트러진다. "최근 한 일" 목록이 이걸 읽는다 — 무엇을 이미 했고 무엇을
        #   다시 해야 하는지가 이 툴에서 가장 자주 잃는 감각이라(2026-08-14 지적:
        #   "영상을 렌더링한 건지 그 앞선 슬라이드를 렌더링한 건지 모르겠다"),
        #   기록을 남기는 쪽이 맞다.
        "at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "cost_usd": round(float(cost_usd), 4),
        "status": status,
        "warnings": warnings or [],
        "data": data,
    }
    ws.write_json(cache_path(pid, slug, stage), env)
    return env


def cached_data(pid: int, slug: str, stage: str) -> Any:
    env = read_cache(pid, slug, stage)
    return (env or {}).get("data")


def outline_of(pid: int, slug: str) -> Dict[str, Any]:
    """**실제로 쓸** 목차 — b2 가 낸 것 위에 사람 손편집을 얹는다.

    ★ Claude 는 목차를 **처음 만들 때만** 쓴다. 제목을 다듬거나 장을 쪼개고 합치는
      일은 그다음에 온다. 그때 다시 해야 하는 것은 목차가 아니라 **그 장의 몸통**이다.

    그래서 원고를 쓰는 곳(b3)도, 조립하는 곳(b6)도 b2 캐시를 직접 읽지 않고 여기를
    읽는다. 한 곳에서만 병합해야 화면에 보이는 목차와 원고에 박히는 목차가 안 갈린다.

    손편집은 **`data_id` 를 키로 하는 dict** 다(배열이 아니다). 배열이면 제목 하나만
    고쳐도 나머지 전부를 같이 보내야 하고, 그 사이에 장이 바뀌면 남의 값을 덮어쓴다.
    """
    base = dict(cached_data(pid, slug, "b2-outline") or {})
    slides: List[Dict[str, Any]] = [dict(s) for s in (base.get("slides") or [])]
    ov = ws.load_overrides(pid, slug)
    patch: Dict[str, Any] = ov.get("slides") or {}
    dropped = set(ov.get("dropped") or [])

    out: List[Dict[str, Any]] = []
    for s in slides:
        did = s.get("data_id")
        if did in dropped:                     # 사람이 뺀 장 — 원장에는 남는다
            continue
        for k, v in (patch.get(did) or {}).items():
            s[k] = v
        out.append(s)

    # 사람이 새로 만든 장은 목차 뒤가 아니라 **`after` 가 가리키는 자리**에 꽂는다
    for did, add in (ov.get("added") or {}).items():
        one = dict(add or {})
        one["data_id"] = did
        after = one.pop("after", None)
        idx = next((i + 1 for i, s in enumerate(out) if s.get("data_id") == after),
                   len(out))
        out.insert(idx, one)

    base["slides"] = out
    for k in ("title", "book", "groups"):
        if k in ov:
            base[k] = ov[k]
    return base


# ── 해시 ───────────────────────────────────────────────────────────────────
def _canonical(obj: Any) -> str:
    """키 정렬 + 고정 구분자. dict 순서가 바뀌었다고 stale 이 되면 안 된다."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _prompt_text(name: Optional[str]) -> str:
    if not name:
        return ""
    p = PROMPTS / name
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return f"<missing:{name}>"


@dataclass
class Stage:
    key: str                      # "b2-outline"
    label: str                    # "장 나누기"
    step: str                     # workspace.STEPS 키
    kind: str                     # "det"(결정론) | "claude" | "ext"(외부 프로세스)
    deps: List[str] = field(default_factory=list)
    prompt: Optional[str] = None          # llm/prompts/<name>
    reads: List[str] = field(default_factory=list)   # project.json 에서 읽는 키
    code_version: int = 1
    run: Optional[Callable[..., Any]] = None         # None = 아직 구현 전

    @property
    def is_claude(self) -> bool:
        return self.kind == "claude"

    def input_hash(self, pid: int, slug: str, project: Dict[str, Any]) -> str:
        payload = {
            "code_version": self.code_version,
            "prompt": _prompt_text(self.prompt),
            "project": {k: project.get(k) for k in sorted(self.reads)},
            "deps": {d: cached_data(pid, slug, d) for d in sorted(self.deps)},
        }
        return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:32]


# ── 스테이지 정의 ──────────────────────────────────────────────────────────
# 순서 = 화면에 보이는 순서 = 실행 순서.
#
#   b1 책에서 글 뽑기 → b2 장 나누기 → b3 몸통 쓰기 → b4 그림
#                    → b5 이미지 프롬프트 → b6 조립 → b7 실측 → b8 내보내기
#
# ★ b7(실측)이 b8(내보내기) **앞**이다. 규약을 어긴 원고를 내보내면 repo #1 이
#   받아서 장이 통째로 비거나 글자 크기가 장마다 들쭉날쭉해진다. 그 사실을
#   저쪽에서 알게 되면 이미 늦다 — 여기서 걸러야 한다.
_DEFS: List[Stage] = [
    # 책은 안 바뀐다. 그래서 결정론이고, 다시 돌려도 돈이 안 든다.
    Stage("b1-pdf", "책에서 글 뽑기", "source", "det",
          reads=["pdfs", "drop_head", "drop_tail"], code_version=1),
    # ★ 장 나누기가 곧 슬라이드 나누기다(규약 2-2: h3 개수 = 슬라이드 개수).
    #   `slide_budget` 을 읽는다 — 예산을 바꾸면 이 단계가 stale 이 되어야 한다.
    Stage("b2-outline", "장 나누기", "outline", "claude",
          deps=["b1-pdf"], prompt="outline.md",
          reads=["title", "book", "id_prefix", "slide_budget", "models"],
          code_version=1),
    # ★ b2 캐시가 아니라 `outline_of()` 를 읽는다. 그래서 손편집이 낡음의 이유가
    #   되도록 `outline_rev` 를 같이 읽는다 — 제목을 고쳐 놓고 "할 일 없음" 이면
    #   사람이 무엇을 믿어야 할지 알 수 없다.
    Stage("b3-write", "몸통 쓰기", "draft", "claude",
          deps=["b1-pdf", "b2-outline"], prompt="write.md",
          reads=["title", "book", "tone", "outline_rev", "models"],
          code_version=1),
    Stage("b4-figure", "그림", "figure", "claude",
          deps=["b3-write"], prompt="figure.md",
          reads=["outline_rev", "models"], code_version=1),
    # ★ 원장에 있고 몸통 해시가 같은 장은 **부르지 않는다.** 돈도 돈이지만,
    #   같은 장의 프롬프트가 이유 없이 바뀌면 이미 그려 둔 그림과 어긋난다.
    Stage("b5-imgprompt", "이미지 프롬프트", "images", "claude",
          deps=["b3-write"], prompt="imgprompt.md",
          reads=["title", "book", "image", "models"], code_version=1),
    Stage("b6-assemble", "원고 조립", "export", "det",
          deps=["b3-write", "b4-figure", "b5-imgprompt"],
          reads=["title", "book", "slug", "outline_rev"], code_version=1),
    # playwright 로 실제 브라우저에 띄워 잰다. 자로 재지 않은 "규약을 지켰다"는
    # 말은 믿을 것이 못 된다 — 규약의 숫자가 전부 픽셀이기 때문이다.
    Stage("b7-check", "실측 검증", "export", "ext",
          deps=["b6-assemble"], reads=["manuscript"], code_version=1),
    Stage("b8-export", "내보내기", "export", "det",
          deps=["b6-assemble", "b7-check"],
          reads=["title", "book", "slug", "image"], code_version=1),
]

STAGES: Dict[str, Stage] = {s.key: s for s in _DEFS}
ORDER: List[str] = [s.key for s in _DEFS]


# ── 상태 ───────────────────────────────────────────────────────────────────
def stage_states(pid: int, slug: str, project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """화면의 스테이지 그리드가 쓰는 것. missing / stale / fresh / degraded."""
    out: List[Dict[str, Any]] = []
    blocked_by: Optional[str] = None

    for key in ORDER:
        st = STAGES[key]
        env = read_cache(pid, slug, key)
        want = st.input_hash(pid, slug, project)

        if env is None:
            state = "missing"
        elif env.get("input_hash") != want:
            state = "stale"
        elif env.get("status") == "degraded":
            state = "degraded"
        elif env.get("status") == "skipped":
            state = "skipped"
        else:
            state = "fresh"

        # 상위가 아직 안 돌았으면 이 스테이지는 시작할 수 없다
        missing_deps = [d for d in st.deps
                        if (read_cache(pid, slug, d) or {}).get("data") is None]

        out.append({
            "key": key,
            "label": st.label,
            "kind": st.kind,
            "step_dir": ws.STEPS[st.step][0],
            "deps": st.deps,
            "state": state,
            "blocked": bool(missing_deps),
            "missing_deps": missing_deps,
            "implemented": st.run is not None,
            # ★ Claude 스테이지는 stale 이어도 자동 실행 대상이 아니다
            "auto": (not st.is_claude) and state in ("missing", "stale") and not missing_deps,
            "cost_usd": (env or {}).get("cost_usd", 0.0),
            "model": (env or {}).get("model", ""),
            "warnings": (env or {}).get("warnings", []),
        })
        if blocked_by is None and state != "fresh":
            blocked_by = key

    return out


def total_cost(pid: int, slug: str) -> float:
    return round(sum((read_cache(pid, slug, k) or {}).get("cost_usd", 0.0)
                     for k in ORDER), 4)
