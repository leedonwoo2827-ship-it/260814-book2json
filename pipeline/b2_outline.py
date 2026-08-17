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

from core import book as bk, config, narration as nr, workspace as ws
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
        # 표지와 마무리에서 할 말. **화면이 되지는 않지만 소리는 난다** —
        # 발표 쇼케이스가 표지 한 장과 마무리 한 장을 앞뒤에 붙이는데, 거기서
        # 아바타가 입을 다물고 있으면 영상이 어색하게 시작하고 뚝 끊긴다.
        "intro": {"type": "string"},
        "outro": {"type": "string"},
        "dropped": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "groups", "slides", "intro", "outro", "dropped"],
    "additionalProperties": False,
}

_ID_OK = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")

# 문장 끝이 하십시오체인가. 「~습니다·~입니다·~까요·~십시오」로 끝나면 존댓말이다.
_POLITE = re.compile(r"(니다|니까|까요|세요|십시오|군요|는데요|지요|죠)$")
# 해라체 끝맺음 — 평서형 `-다` 와 물음형 `-는가/-인가`. 소리로 들으면 반말처럼 들린다.
_CASUAL = re.compile(r"(다|는가|은가|인가|던가)$")
# 용언으로 끝난 문장의 끝 글자. 여기 없으면 체언(명사)으로 끊은 것이다.
_VERB_END = ("다", "요", "까", "가", "오", "죠", "네", "군", "라", "자", "지")

# ★ 문장을 가르는 마침표. **소수점을 문장 끝으로 세지 않는다** — 「물가상승률은
#   2.3% 입니다」가 「…연 2」 와 「3% 입니다」 두 문장으로 잘려서, 멀쩡한 장이
#   「체언으로 끊었다」고 잡혔다(2026-08-14 19장에서 6건이 전부 이것이었다).
_SPLIT = re.compile(r"(?<!\d)[.!?]+\s*|[.!?]+(?!\d)\s*")


def _sentences(say: str) -> List[str]:
    return [x.strip() for x in _SPLIT.split(say or "") if x and x.strip()]


def _casual_ratio(say: str) -> float:
    """해라체 문장의 비율. 「~이다·~한다·~인가」로 끝나는 문장이 몇 할인가.

    ★ 고치려 들지 않는다. 우리말 어미를 코드로 바꾸면 「않는다→않습니다」는 맞아도
      인용문이나 물음이 뭉개진다. **세어서 사람에게 말하는 데까지만** 한다.
    """
    parts = _sentences(say)
    if not parts:
        return 0.0
    casual = sum(1 for p in parts if _CASUAL.search(p) and not _POLITE.search(p))
    return casual / len(parts)


def _noun_end(say: str) -> int:
    """체언(명사)으로 끊은 문장 수. 「…재는 두 길.」 처럼 끝난 것들.

    존댓말로 말하는 중에 이런 문장이 하나 끼면 거기서만 말이 뚝 끊긴 것처럼
    들린다. 화면에 적는 줄에서는 맞는 문체라 모델이 자꾸 섞는다.
    """
    return sum(1 for p in _sentences(say) if not p.endswith(_VERB_END))


def build_brief(project: Dict[str, Any], md: str, heads: List[Dict[str, Any]],
                want: Dict[str, Any]) -> str:
    """모델에게 보낼 재료 한 덩이.

    ★ 본문을 **자르지 않는다.** 한 장이 4~6만 자(2~3만 토큰)라 통째로 들어간다.
      앞부분만 보내면 뒤쪽 절이 통째로 목차에서 빠지는데, 그것을 사람이 알아채려면
      책과 목차를 나란히 놓고 세어야 한다 — 아무도 안 한다.

    ★ **목표 영상 길이를 숫자로 박는다.** 이 브리프가 「한두 문장」만 시켰을 때
      19장이 5분 30초로 나왔다. 모델은 「충분히 길게」 같은 말로는 안 늘린다 —
      장마다 몇 자인지 적어 줘야 그만큼 쓴다.
    """
    hint = bk.outline_hint(heads)
    budget = int(project.get("slide_budget") or 0) or want["slides"]
    prefix = project.get("id_prefix") or "bk"
    lines = [
        f"# 책", project.get("book") or "(제목 없음)",
        f"\n# 이 장", project.get("title") or "(제목 없음)",
        f"\n# 목표 영상 길이",
        f"**{want['minutes']}~{want['minutes_max']}분.** 읽는 속도가 "
        f"{want['chars_per_min']}자/분(5.5자/초)이므로, `say` 를 전부 합쳐 "
        f"**{want['say_total']:,}자 이상 {want['say_max']:,}자까지** 써야 그 길이가 나온다.",
        f"모자란 것은 다시 만들어야 하고 넘치는 것은 장을 빼면 되니, **상한 쪽을 노려라.**",
        f"\n# 장 예산", f"{budget}장 (±3)",
        f"\n# 장당 `say` 분량",
        f"**{want['say_per_slide']}~{int(want['say_per_slide'] * nr.RANGE_MAX)}자** — "
        f"한 장을 {want['seconds_per_slide']}~"
        f"{round(want['seconds_per_slide'] * nr.RANGE_MAX)}초 동안 말하는 양이다. "
        f"짧게 쓰면 영상이 목표의 절반으로 나온다.",
    ]
    # ★ 300자가 넘어가면 「네 토막」만으로는 안 찬다. 그때 사람이 하는 짓은 같은 말을
    #   바꿔 말하며 늘리는 것인데, 그러면 듣는 쪽이 먼저 안다. 무엇으로 채울지를
    #   **재료로** 일러 준다 — 전부 책 안에 있는 것들이다.
    if want.get("long_form"):
        lines += [
            f"\n# 이 원고는 **긴 대본**이다",
            f"한 장을 {want['seconds_per_slide']}초 동안 말한다. 장을 더 만들어 나누는 "
            f"길은 이미 닫혀 있다 — 화면을 늘리는 대신 **한 화면에서 깊이 말하기로** "
            f"정한 원고다. 늘릴 때는 아래 순서로 **책에 있는 것**을 꺼내 채워라.",
            "1. 그 개념이 왜 필요했는지 — 책이 적어 둔 배경이나 역사",
            "2. 책의 사례를 **끝까지** 따라가기. 숫자가 있으면 숫자로",
            "3. 반대 경우 · 예외 · 성립하지 않는 조건",
            "4. 흔한 오해를 짚어 바로잡기 (책이 짚은 것만)",
            "5. 앞 장에서 말한 것과 이어 붙이기",
            "★ 같은 말을 바꿔 말하며 늘리지 마라. 늘릴 재료가 없으면 그 장은 짧게 두고, "
            "재료가 남는 옆 장을 길게 써라 — **합이 맞으면 된다.**",
        ]
    lines += [
        f"\n# 이름표 앞머리", f"`{prefix}-` 로 시작할 것 (예: {prefix}-03)",
    ]
    if hint:
        lines += ["\n# 책이 매긴 목차 — 참고만 할 것",
                  "책의 절 하나가 여덟 쪽이면 여덟 장짜리다. 그대로 베끼지 마라.",
                  "```", hint, "```"]
    lines += ["\n# 본문", md]
    return "\n".join(lines)


def repair(raw: Dict[str, Any], prefix: str,
           want: Dict[str, Any] | None = None) -> tuple[Dict[str, Any], List[str]]:
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

    # ★ **말 길이는 수리하지 않는다 — 셀 뿐이다.** 이름표나 그림 종류는 코드가
    #   지어 채워도 맞지만, 짧은 `say` 를 코드가 늘릴 방법은 없다(늘리면 지어내는
    #   것이다). 대신 몇 장이 얼마나 짧은지 남겨서, 사람이 다시 돌릴지 목차 화면에서
    #   손으로 채울지 고르게 한다.
    # ★ 말투 검사. 프롬프트로 시켜도 모델은 문어체(해라체)로 돌아가곤 한다 —
    #   눈으로 읽는 글에는 그게 맞아서다. 소리로 들으면 반말처럼 들린다
    #   (2026-08-14 지적). 고치지는 못하고 **세어서 말한다.**
    casual = [s["data_id"] for s in slides if _casual_ratio(s["say"]) > 0.4]
    if casual:
        warn.append(f"말투가 해라체(「~이다」)인 장 {len(casual)}개 — 아바타가 읽으면 "
                    f"반말처럼 들립니다: " + ", ".join(casual[:8]))
    nouny = [s["data_id"] for s in slides if _noun_end(s["say"])]
    if nouny:
        warn.append(f"체언으로 끊은 문장이 있는 장 {len(nouny)}개 — 「…두 길.」 이 아니라 "
                    f"「…두 가지입니다.」 로 맺어야 합니다: " + ", ".join(nouny[:8]))

    if want:
        floor = int(want["say_per_slide"] * 0.6)
        short = [s["data_id"] for s in slides if nr.count(s["say"]) < floor]
        got = nr.count_all(s["say"] for s in slides)
        if short:
            warn.append(f"말이 짧은 장 {len(short)}개(장당 {floor}자 미만): "
                        + ", ".join(short[:8]) + ("…" if len(short) > 8 else ""))
        if got < want["say_total"] * 0.85:
            warn.append(f"say 를 다 합쳐 {got:,}자 — {nr.clock(got)}짜리입니다"
                        f" (목표 {want['minutes']}분 · {want['say_total']:,}자)")

    groups = [{"num": str(g.get("num") or ""), "title": (g.get("title") or "").strip()}
              for g in (raw.get("groups") or [])]
    # 아무 장도 안 딸린 묶음은 목차에 갈래만 만들고 아무것도 안 담는다 — 뺀다.
    used = {s["group"] for s in slides}
    kept = [g for g in groups if g["num"] in used]
    if len(kept) != len(groups):
        warn.append(f"장이 없는 묶음 {len(groups) - len(kept)}개를 뺐습니다")

    return {"title": (raw.get("title") or "").strip(), "groups": kept,
            "slides": slides,
            "intro": (raw.get("intro") or "").strip(),
            "outro": (raw.get("outro") or "").strip(),
            "dropped": [str(x) for x in (raw.get("dropped") or [])]}, warn


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

    # 목표 길이 → 장 수 · 장당 말 길이. 화면(새 원고 표)과 **같은 계산**이다.
    want = nr.plan_of(project, int(src.get("chars") or len(md)))

    job.progress(0, 1, f"목차 세우는 중 — {want['minutes']}분 · {want['slides']}장 목표")
    p = ClaudeProvider(
        model=(project.get("models") or {}).get("outline") or cfg["models"]["outline"],
        effort=cfg["effort"]["outline"],
        budget_usd=cfg["budget_usd"]["per_stage"],
        on_activity=lambda s: job.progress(0, 1, s),
    )
    raw = p.structured(system,
                       [{"role": "user",
                         "content": build_brief(project, md, src.get("heads") or [], want)}],
                       schema=SCHEMA)
    job.progress(1, 1, "정리")

    data, warn = repair(raw, prefix, want)
    if not data["slides"]:
        raise RuntimeError("장이 하나도 안 나왔습니다. 본문이 제대로 뽑혔는지 확인하세요")

    ws.write_json(ws.outline_path(pid, slug, create=True), data)

    n_tab = sum(1 for s in data["slides"] if s["visual"] == "table")
    said = nr.count_all(s["say"] for s in data["slides"])
    job.add_log(f"{len(data['slides'])}장 · 묶음 {len(data['groups'])}개 "
                f"· 그림 {len(data['slides']) - n_tab}개 · 표 {n_tab}개 · ${p.last_cost_usd:.3f}")
    # ★ 여기서 이미 길이가 정해진다. 몸통·그림에 돈을 쓰기 **전에** 알려 준다 —
    #   5분짜리로 판명되는 자리가 영상이 나온 뒤여서는 안 된다.
    job.add_log(f"말 {said:,}자 → {nr.clock(said)} "
                f"(목표 {want['minutes']}분 · {want['say_total']:,}자 · 장당 "
                f"{said // max(1, len(data['slides']))}자/{want['say_per_slide']}자)")
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
