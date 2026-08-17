# -*- coding: utf-8 -*-
"""분량 계산 — **영상 길이를 정하는 것은 `data-say` 총량이다.**

2026-08-14 신고: 19장 원고로 만든 영상이 **5분 30초**였다. 15분짜리를 기대했는데
그 절반도 안 됐다. 원인을 세 편에서 재 봤다(공백 제외):

    19장  27장 · say 2,419자 · 화면 3,333자  →  실제 5분 30초
    20장  28장 · say 2,007자 · 화면 3,680자
    21장  24장 · say 2,840자 · 화면 3,335자

즉 길이를 정하는 것은 화면에 적힌 줄이 아니라 **말하는 글**이다. 그 글이 장당
89자였으니 어떻게 붙여도 짧을 수밖에 없었다.

★ 처음엔 저 5분 30초에서 440자/분을 거꾸로 셈해 썼다. **틀린 셈이었다** — 그때
  저쪽은 우리 `data-say` 를 안 읽고 자기가 지은 내레이션을 읽고 있었다. 지금은
  읽는 쪽이 알려 준 값(5.5자/초 = 330자/분)을 쓴다.

그러면 왜 짧았나 — `llm/prompts/outline.md` 가 `say` 를 「한두 문장」으로 시켰기
때문이다. 장당 89자짜리 스물일곱 장은 어떻게 붙여도 6분을 못 넘긴다. **목표 길이를
정하고 거기서 거꾸로 장 수와 장당 말 길이를 뽑는다.** 그게 이 파일이다.

★ 숫자를 여기 한 곳에만 둔다. 새 원고 화면의 표(`static/js/start.js`)도, 목차를
  세우는 프롬프트(`b2-outline`)도, 다 됐을 때 몇 분짜리인지 세는 자리(`b6`·`b7`)도
  전부 이 모듈을 부른다. 화면이 「15분」이라 해 놓고 프롬프트는 딴 수를 받는 일이
  없어야 한다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

# ── 상수 ───────────────────────────────────────────────────────────────────
#
# 자/분. **330 = 5.5자/초.** 영상을 만드는 쪽이 알려 준 값이다(2026-08-14):
#
#     분 = 공백 뺀 글자 수 ÷ 5.5 ÷ 60
#     5,000자 = 약 15분 · 6,600자 = 약 20분
#
# ★ 여기 처음엔 420 이 적혀 있었다. 19장 영상이 5분 30초였고 그 원고의 `say` 가
#   2,419자였으니 440자/분이라고 거꾸로 셈한 값이었다. **그 셈이 틀렸다** — 그때
#   저쪽은 `data-say` 를 읽지 않고 자기가 지은 내레이션을 읽고 있었다. 우리 글자
#   수와 그 영상 길이 사이에는 아무 관계가 없었던 것이다.
#
#   실제로 읽는 쪽이 말해 준 값이 유일한 근거다. 재는 자와 읽는 자가 다르면
#   재는 쪽이 아니라 **읽는 쪽의 자**를 써야 한다.
CHARS_PER_MIN = 330

# 목표는 점이 아니라 **구간**이다 — 「15~20분」. 넘치는 것은 괜찮고(씬을 빼면 된다)
# 모자란 것은 다시 만들어야 한다. 그래서 하한을 목표로 잡고 상한까지 허용한다.
RANGE_MAX = 1.33

# 장 하나에서 말할 글자 수. **초로 환산해서 정한 값이다**(330자/분 = 5.5자/초).
SAY_PER_SLIDE = 155          # 28초. 우리말로 서너 문장
SAY_PER_SLIDE_MIN = 110      # 20초. 이보다 짧으면 「한두 문장」으로 되돌아간 것이다
SAY_PER_SLIDE_MAX = 190      # 35초. 장을 늘려서라도 여기까지는 맞춘다
SAY_PER_SLIDE_HARD = 470     # 85초. 이 위로는 한 화면이 너무 오래 머문다

# ★ **장을 늘리는 것은 30분치까지다.** 그 위로는 장을 더 만들지 않고 장당 대본만
#   늘린다(2026-08-14 지시: "슬라이드 수는 30분까지만 늘리고 그다음부터는 안 늘어나는").
#
#   60분은 그래서 **30분과 같은 장 수에 대본이 두 배**다. 105장짜리 목차를 한 번에
#   짜면 뒤쪽이 성글어지고, 확인할 화면과 그려야 할 그림이 두 배가 된다 — 얻는 것보다
#   잃는 것이 크다. 대신 한 장을 68초 동안 말하는 강의가 된다.
SLIDE_GROWTH_MAX_MIN = 30

# ★ 장 수는 **원문이 정한다.** 목표 길이가 정하는 것이 아니다.
#
#   길이가 모자랄 때 슬라이드를 늘리는 것은 쉬운 답이지만 답이 아니다
#   (2026-08-14 지적: "슬라이드 수를 무작정 늘리는 것도 답은 아니죠"). 장을 늘리면
#   확인할 화면과 그려야 할 그림이 같이 늘고, 원문 근거가 얇아져 지어내기 시작한다.
#   그래서 **먼저 장당 말을 늘리고**, 그것이 34초를 넘길 때만 장을 하나 더 만든다.
#
#   1,700자당 한 장은 새뮤얼슨 19·20장 실측에서 나온 값이다(44,093자 → 27장).
SOURCE_PER_SLIDE = 1700
SOURCE_PER_SLIDE_MIN = 380   # 이보다 잘게 쪼개면 근거가 모자라 지어낸다
MIN_SLIDES = 12

# 요약 비율(= 말할 글자 ÷ 원문)이 이 선을 넘으면 원문을 거의 통째로 읽는 셈이다.
RATIO_WARN = 0.60

# 장당 이만큼을 넘으면 「긴 대본」이다 — 프롬프트가 쓰는 법을 더 붙인다(42초).
LONG_FORM_FROM = 230

# 목차 한 번에 이만큼을 넘게 쓰게 되면 미리 말해 준다. b2 는 **한 번의 호출**로
# 목차와 대본을 통째로 내는데, 출력이 길수록 뒤쪽이 성글어진다(b3 를 여덟 장씩
# 묶어 부르게 만든 것과 같은 문제다. 목차는 앞뒤가 서로를 봐야 해서 못 쪼갠다).
BIG_OUTLINE_CHARS = 15000

# 고를 수 있는 목표 길이. **15분이 기본**이고 나머지는 옵션이다.
TARGETS: Sequence[int] = (15, 30, 60)
DEFAULT_MIN = 15


# ── 세기 ───────────────────────────────────────────────────────────────────
def count(text: str) -> int:
    """공백을 뺀 글자 수. **재는 방법을 한 곳에 둔다** — 어디서는 공백을 세고
    어디서는 안 세면 같은 원고가 화면마다 다른 길이로 보인다."""
    return len(re.sub(r"\s+", "", text or ""))


def count_all(texts) -> int:
    return sum(count(t) for t in texts if t)


def minutes_of(say_chars: int) -> float:
    return round((say_chars or 0) / CHARS_PER_MIN, 1)


def clock(say_chars: int) -> str:
    """「5분 30초」. 사람이 영상 재생시간과 나란히 놓고 보는 값이라 초까지 적는다."""
    total = int(round((say_chars or 0) / CHARS_PER_MIN * 60))
    return f"{total // 60}분 {total % 60:02d}초"


# ── 계획 ───────────────────────────────────────────────────────────────────
def plan(source_chars: int, minutes: int = DEFAULT_MIN) -> Dict[str, Any]:
    """원문 글자 수와 목표 길이로 **장 수 · 장당 말 길이**를 뽑는다.

    순서가 중요하다:

        1. 장 수는 **원문**이 정한다 (1,700자당 한 장)
        2. 말할 총량은 **목표 길이**가 정한다 (분 × 330자)
        3. 장당 말 = 총량 ÷ 장 수. 이게 34초를 넘길 때만 **그제서야** 장을 늘린다
        4. 단, 장을 늘리는 것은 **30분치까지**다. 그 위로는 대본만 늘어난다

    그래서 15분을 골라도 장 수는 지금과 크게 안 달라진다. 달라지는 것은 장마다
    말하는 양이다 — 89자(한두 문장)에서 230자(대여섯 문장)로. 60분은 30분과 **같은
    장 수에 대본이 두 배**다.
    """
    src = max(0, int(source_chars or 0))
    mins = max(1, int(minutes or DEFAULT_MIN))
    say_total = mins * CHARS_PER_MIN

    base = max(MIN_SLIDES, round(src / SOURCE_PER_SLIDE)) if src else MIN_SLIDES
    # 장을 늘리는 근거는 목표 전체가 아니라 **30분치까지**다.
    grow_to = min(mins, SLIDE_GROWTH_MAX_MIN) * CHARS_PER_MIN
    need = -(-grow_to // SAY_PER_SLIDE_MAX)            # 올림 나눗셈
    slides = max(base, need)
    # 원문이 얇으면 장을 더 못 늘린다 — 늘리면 근거 없는 장이 생긴다.
    cap = max(MIN_SLIDES, src // SOURCE_PER_SLIDE_MIN) if src else slides
    slides = min(slides, cap)

    per = int(round(say_total / slides))
    ratio = (say_total / src) if src else 0.0
    added = max(0, slides - base)

    warn: List[str] = []
    # ★ 한두 장 늘어난 것은 할 말이 아니다. **원문이 정한 장 수의 1.5배**를 넘을 때만
    #   말한다 — 그때부터는 확인할 화면과 그려야 할 그림이 눈에 띄게 늘어난다.
    if added and slides > base * 1.5:
        warn.append(f"원문 기준 {base}장인데 {slides}장이 됩니다 — "
                    f"장이 {slides / base:.1f}배로 늘고 그림도 그만큼 늘어납니다")
    # 장당 말이 34초를 넘는 것은 **30분 위에서는 의도한 것**이다(장을 안 늘리기로
    # 했으니 말이 길어질 수밖에 없다). 그건 표에 숫자로 적히니 경고가 아니고,
    # 86초를 넘어갈 때만 말한다 — 그때는 한 화면이 정말 오래 머문다.
    if per > SAY_PER_SLIDE_HARD:
        warn.append(f"장당 {per}자 — 한 화면을 {per / CHARS_PER_MIN * 60:.0f}초 "
                    f"보고 있게 됩니다. 원문이 얇아서 그렇습니다")
    if ratio > RATIO_WARN:
        warn.append(f"원문의 {ratio * 100:.0f}% 를 말하게 됩니다 — 요약이 아니라 낭독에 가깝습니다")
    if say_total > BIG_OUTLINE_CHARS:
        warn.append(f"목차와 대본 {say_total:,}자를 한 번에 만들게 됩니다 — "
                    f"오래 걸리고, 뒤쪽 장의 대본이 앞쪽보다 성글 수 있습니다")

    return {
        "minutes": mins,
        "minutes_max": round(mins * RANGE_MAX),
        "say_total": say_total,          # 이만큼 말해야 그 길이가 나온다(하한)
        "say_max": int(say_total * RANGE_MAX),   # 여기까지는 넘쳐도 괜찮다
        "slides": slides,                # 목차(b2)가 만들 장 수
        "base_slides": base,             # 원문만 보고 정한 장 수(늘리기 전)
        "added_slides": added,           # 길이 때문에 더한 장
        "say_per_slide": per,            # 장마다 이만큼
        "seconds_per_slide": round(per / CHARS_PER_MIN * 60),
        # 장을 안 늘리고 대본만 늘린 구간인가(30분 위). 프롬프트가 이걸 보고
        # 「긴 대본 쓰는 법」을 더 붙인다.
        "long_form": per >= LONG_FORM_FROM,
        "source_chars": src,
        "ratio": round(ratio, 4),
        "chars_per_min": CHARS_PER_MIN,
        "clock": clock(say_total),
        "warnings": warn,
    }


def options(source_chars: int, targets: Sequence[int] = TARGETS) -> List[Dict[str, Any]]:
    """새 원고 화면의 표. **기본은 15분**이고 30·60분은 옵션이다."""
    return [{**plan(source_chars, m), "recommended": m == DEFAULT_MIN}
            for m in targets]


def target_of(project: Dict[str, Any]) -> int:
    """프로젝트가 노리는 길이. 옛 원고에는 이 값이 없어서 기본값으로 읽힌다."""
    try:
        m = int(project.get("target_min") or 0)
    except (TypeError, ValueError):
        m = 0
    return m if m > 0 else DEFAULT_MIN


def plan_of(project: Dict[str, Any], source_chars: int) -> Dict[str, Any]:
    return plan(source_chars, target_of(project))


def label(want: Dict[str, Any], say_chars: int, chapter: str = "") -> str:
    """원고 맨 위에 박을 한 줄. **목표가 원고에 안 적혀 있으면 아무도 모른다.**

    2026-08-14, 영상 쪽 부탁:

        "글자 수는 앱이 셀 수 있습니다. 그런데 목표가 몇 분인지는 원고에 없으면
         알 수가 없습니다. 그래서 음성을 다 구운 뒤에야 「짧다」를 알게 됩니다."

    맞는 말이다. 우리는 목표를 알고 저쪽은 모른다 — **아는 쪽이 적어 보내야 한다.**
    """
    ch = (chapter or "").strip()
    return (f"{ch + ' · ' if ch else ''}"
            f"목표 {want['minutes']}~{want['minutes_max']}분 · "
            f"data-say {say_chars:,}자".replace(",", ""))


def verdict(say_chars: int, want: Dict[str, Any]) -> Dict[str, Any]:
    """지금 원고가 목표에 닿았나. **다 만든 뒤에 알면 늦으므로** 조립할 때 센다."""
    total = int(want.get("say_total") or 0)
    got = int(say_chars or 0)
    short = total and got < total * 0.85
    return {
        "say_chars": got,
        "clock": clock(got),
        "minutes": minutes_of(got),
        "target_min": want.get("minutes"),
        "target_chars": total,
        "pct": round(got / total * 100) if total else 0,
        "short": bool(short),
        "note": (f"목표 {want.get('minutes')}~{want.get('minutes_max')}분"
                 f"({total:,}자 이상)인데 {clock(got)}({got:,}자)입니다"
                 if short else
                 f"{clock(got)} — 목표 {want.get('minutes')}~{want.get('minutes_max')}분"),
    }
