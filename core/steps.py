# -*- coding: utf-8 -*-
"""순서 번호 — **이 표가 유일한 출처다.**

구조는 `260812-summary-shocase/core/steps.py` 그대로다. 거기서 얻은 규칙:
자리마다 이름이 조금씩 달라도 **번호가 둘을 잇는다.** 다음 숫자를 누르면 된다.

★ 번호는 실행 순서(registry.ORDER)가 아니라 **사람이 누르는 순서**다.
  여기서는 둘이 거의 같지만, 같아 보인다고 registry 를 직접 읽지 않는다 —
  나중에 순서가 갈릴 때 화면이 조용히 틀린 번호를 보여 주게 된다.
★ 이름은 **단계 라벨의 낱말을 그대로** 쓴다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

STEPS: List[Dict[str, Any]] = [
    {"n": 1, "name": "책에서 글 뽑기",
     "tip": "PDF 를 쪽별로 읽어 붙입니다. 돈은 안 듭니다",
     "keys": ["b1-pdf"]},
    {"n": 2, "name": "장 나누기와 대본",
     "tip": "h3 하나가 슬라이드 한 장 — 여기서 장 수와 영상 길이가 정해집니다",
     "keys": ["b2-outline"]},
    {"n": 3, "name": "몸통 쓰기",
     "tip": "장마다 여섯 줄 안쪽으로. 넘치면 장을 쪼갭니다",
     "keys": ["b3-write", "b4-figure"]},
    # ★ 4번이었던 「이미지 프롬프트」가 빠졌다 — 그림 지시는 다른 에이전트가
    #   만든다(2026-08-14). 그것을 내보내던 6번도 같이 빠졌다: 남은 산출물(원고·
    #   대본·실측)은 전부 조립·실측이 그 자리에서 파일로 쓴다.
    {"n": 4, "name": "마무리 — 조립하고 재기",
     "tip": "원고 한 파일로 묶고 944×507 을 실제로 잽니다. 돈은 안 듭니다",
     "keys": ["b6-assemble", "b7-check"]},
]

BY_KEY: Dict[str, Dict[str, Any]] = {}
for _s in STEPS:
    for _k in _s["keys"]:
        BY_KEY[_k] = _s

# 손으로 고친 것은 순서에 없다 — 아무 때나 일어난다. 다만 **어느 단계보다 앞이냐**
# 는 정해야 낡음을 판정할 수 있다. 목차·몸통을 손보는 일이므로 마무리(4) 앞이다.
HAND_BEFORE = 4


def of(key: Optional[str]) -> Optional[Dict[str, Any]]:
    """스테이지 키(또는 산출물 파일 이름) → 그 단계. 모르면 None."""
    if not key:
        return None
    hit = BY_KEY.get(key)
    if hit:
        return hit
    s = str(key).lower()
    # 산출물 파일은 전부 마무리 단계가 쓴다(원고·대본은 b6, 실측은 b7).
    if s.endswith(".html") or s.endswith(".json") or s.endswith(".txt"):
        return BY_KEY["b6-assemble"]
    return None


def n_of(key: Optional[str]) -> Optional[int]:
    st = of(key)
    return st["n"] if st else None
