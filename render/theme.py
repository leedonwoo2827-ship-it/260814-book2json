# -*- coding: utf-8 -*-
"""테마 — themeSpec(enum·hex) → CSS 변수. 그리고 브랜드 램프 파생.

두 가지 일을 한다.

1. **브랜드 램프 파생** (`derive_ramp`)
   퍼스널 컬러 hex 하나를 주면 8단 램프를 만든다. 손으로 고르면 반드시 틀리는
   것이 대비비다. IDA 의 램프는 500 에서 갈린다 — ≥500 은 작은 글씨로 읽히고
   ≤400 은 채움 전용이다. 그 사다리를 **숫자로 재현한다**:

       sky-400      2.98   채움 전용 (텍스트 금지)
       sky-500      4.90   라인 아이콘 · 링크 · 포커스 링
       brand        5.55   액션 채움 · 활성
       brand-hover  8.18   눌림 · 앵커

   색조(H)와 채도(S)를 고정하고 명도(L)만 이분탐색해서 목표 대비비를 맞춘다.

2. **themeSpec 검증·수리** (`normalize_theme`)
   Claude 는 마크업이 아니라 **선택지**만 낸다 — enum·hex·작은 정수뿐.
   스펙 밖 값이 와도 거부하지 않고 **수리**한다. 미지 enum은 기본값으로, 잘못된
   hex 는 seed 팔레트로, 대비 미달은 스냅. 무엇을 고쳤는지 warnings 에 남긴다.
   그래야 `"variant":"cinematic"` 같은 환각이 페이지를 깨지 않는다.
"""
from __future__ import annotations

import colorsys
import re
from typing import Any, Dict, List, Tuple

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# 흰 배경 기준 목표 대비비 — IDA 램프에서 측정한 값
TARGETS: Dict[str, float] = {
    "sky-400": 2.98,
    "sky-500": 4.90,
    "brand": 5.55,
    "brand-hover": 8.18,
}
# 틴트 3종은 대비 목표가 없다. 흰색과 섞는 비율로만 만든다.
TINTS: Dict[str, float] = {
    "sky-wash": 0.965,     # 아이콘박스 그라데이션 시작 · 호버 배경
    "brand-wash": 0.915,   # 활성 nav 배경 · 뱃지
    "brand-soft": 0.630,   # 아바타 후광 · ::selection
}


# ── 색 유틸 ────────────────────────────────────────────────────────────────
def hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, round(r))), max(0, min(255, round(g))), max(0, min(255, round(b)))
    )


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: Tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg: str, bg: str = "#ffffff") -> float:
    """WCAG 대비비. 1.0 ~ 21.0"""
    a, b = luminance(hex_to_rgb(fg)), luminance(hex_to_rgb(bg))
    lo, hi = min(a, b), max(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _hsl(hex_: str) -> Tuple[float, float, float]:
    r, g, b = (c / 255.0 for c in hex_to_rgb(hex_))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, s, l


def _from_hsl(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return rgb_to_hex(r * 255, g * 255, b * 255)


def _mix_white(hex_: str, amount: float) -> str:
    """amount=1.0 이면 흰색, 0.0 이면 원색."""
    r, g, b = hex_to_rgb(hex_)
    return rgb_to_hex(
        r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount
    )


def at_contrast(seed: str, target: float, *, bg: str = "#ffffff") -> str:
    """seed 의 색조·채도를 지키면서 목표 대비비에 맞는 명도를 이분탐색으로 찾는다.

    ★ 방향이 배경에 따라 뒤집힌다. 흰 배경에서는 명도가 오를수록 대비가 **낮아지고**,
      어두운 배경에서는 **높아진다.** 한쪽만 가정하면 다크 테마에서 조용히 틀린 색이
      나온다(탐색이 엉뚱한 끝으로 수렴한다). 그래서 배경 밝기로 방향을 먼저 정한다.
    """
    h, s, _ = _hsl(seed)
    dark_bg = luminance(hex_to_rgb(bg)) < 0.18
    lo, hi = 0.0, 1.0
    best, best_err = seed, 1e9
    for _ in range(48):
        mid = (lo + hi) / 2
        cand = _from_hsl(h, s, mid)
        c = contrast(cand, bg)
        err = abs(c - target)
        if err < best_err:
            best, best_err = cand, err
        # 어두운 배경: 대비가 목표보다 크면 더 어둡게(명도 ↓) 가야 한다
        too_high = c > target
        if too_high != dark_bg:
            lo = mid
        else:
            hi = mid
    return best


def _mix_bg(hex_: str, bg: str, amount: float) -> str:
    """배경 쪽으로 섞는다. 라이트면 흰색, 다크면 어두운 바탕으로 수렴한다."""
    r, g, b = hex_to_rgb(hex_)
    br, bg_, bb = hex_to_rgb(bg)
    return rgb_to_hex(r + (br - r) * amount, g + (bg_ - g) * amount, b + (bb - b) * amount)


def derive_ramp(seed: str, *, bg: str = "#ffffff", desat: float = 1.0) -> Dict[str, str]:
    """퍼스널 컬러 hex 하나 → 8단 브랜드 램프.

    `seed` 는 어느 단이어도 된다. 색조만 가져가고 명도는 다시 계산한다.
    `desat` < 1.0 이면 채도를 눌러 **K 가 섞인** 가라앉은 톤이 된다
    (인쇄로 치면 먹을 더 넣는 것). 다크 UI 에서 순색은 형광펜처럼 튄다.
    """
    if not HEX_RE.match(seed or ""):
        seed = "#8e2a3e"
    if desat != 1.0:
        h, s, l = _hsl(seed)
        seed = _from_hsl(h, max(0.0, min(1.0, s * desat)), l)

    ramp = {name: at_contrast(seed, t, bg=bg) for name, t in TARGETS.items()}
    base = ramp["brand"]
    for name, amt in TINTS.items():
        ramp[name] = _mix_bg(base, bg, amt)
    # 웹↔산출물 공유 앵커. 브랜드보다 더 가라앉은 색.
    h, s, _ = _hsl(base)
    anchor_l = 0.82 if luminance(hex_to_rgb(bg)) < 0.18 else 0.20
    ramp["brand-deep"] = _from_hsl(h, max(0.18, s * 0.55), anchor_l)
    return ramp


def ramp_report(ramp: Dict[str, str], *, bg: str = "#ffffff") -> List[str]:
    """대비 사다리가 실제로 맞았는지 확인용."""
    order = ["sky-wash", "brand-wash", "brand-soft", "sky-400",
             "sky-500", "brand", "brand-hover", "brand-deep"]
    out = []
    for k in order:
        v = ramp.get(k, "")
        c = contrast(v, bg) if v else 0
        tgt = TARGETS.get(k)
        mark = "" if tgt is None else f"  목표 {tgt:.2f}"
        out.append(f"  --{k:<12} {v}   대비 {c:5.2f}{mark}")
    return out


# ── 레일(다크 사이드바) 위의 브랜드 ────────────────────────────────────────
# ★ 레일 위에서는 대비 기준면이 `--paper` 가 아니라 `--rail`(#201e1b)이다.
#   같은 브랜드 색을 그대로 얹으면 안 읽힌다 — app.css 머리말이 적어 둔 그대로다.
#   그래서 **레일 배경 기준으로 다시 잰다.** 목표값은 showcase 의 테라코타 레일에서
#   실측한 것(--rail-brand 6.21 · --rail-brand-soft 3.40)을 그대로 쓴다.
RAIL_BG = "#201e1b"
RAIL_TARGETS: Dict[str, float] = {"rail-brand": 6.21, "rail-brand-soft": 3.40}


def derive_rail(seed: str, *, bg: str = RAIL_BG) -> Dict[str, str]:
    """레일 위에서 쓸 브랜드 두 단. 손으로 고르면 반드시 틀리는 것이 대비비다."""
    return {name: at_contrast(seed, t, bg=bg) for name, t in RAIL_TARGETS.items()}


if __name__ == "__main__":  # 파생 결과 눈으로 확인
    import sys

    argv = sys.argv[1:]
    seed = next((a for a in argv if not a.startswith("--")), "#2f6b66")
    on = argv[argv.index("--on") + 1] if "--on" in argv else None

    if on:
        rail = derive_rail(seed, bg=on)
        print(f"seed {seed}  on {on}  →  레일 위 브랜드")
        for k, v in rail.items():
            print(f"  --{k:<16} {v}   대비 {contrast(v, on):5.2f}"
                  f"  목표 {RAIL_TARGETS[k]:.2f}")
    else:
        print(f"seed {seed}  →  브랜드 램프")
        print("\n".join(ramp_report(derive_ramp(seed))))
        print(f"\n레일(#201e1b) 위는:  python render/theme.py \"{seed}\" --on \"{RAIL_BG}\"")


