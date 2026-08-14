# -*- coding: utf-8 -*-
"""book2json.config.json 로더.

**환경변수 → 파일 → 기본값** 순으로 덮는다. 파일에 없는 키가 있어도 기본값으로
메워지므로, 설정 파일을 갱신하지 않은 동료의 PC 에서도 그냥 돈다.
구조는 `260812-summary-shocase/core/config.py` 그대로다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("BOOK2JSON_CONFIG") or (APP_DIR / "book2json.config.json"))

# ★ 내 PC 전용 값은 여기로 뺀다 — **배포본에 개인 절대경로가 나가면 안 된다.**
#   기본 PDF 폴더처럼 사람마다 다른 것이 여기 산다. gitignore 대상이고,
#   없으면 그냥 없는 대로 돈다.
LOCAL_PATH = APP_DIR / "book2json.config.local.json"

DEFAULTS: Dict[str, Any] = {
    # ★ 5178 은 260812-summary-shocase 가 쓴다. 5179 도 이미 다른 것이 물고 있어
    #   자리를 옮겼다. 5187 은 5178 의 뒤 두 자리를 바꾼 수라 두 앱을 나란히
    #   적어도 눈에 띄고, 잘못 친 포트로 남의 앱에 들어갈 일이 없다.
    "port": 5187,
    "auth": "claude-code",

    "models": {
        "outline": "claude-opus-5",     # 장 나누기 — 판단이 제일 어렵다
        "write":   "claude-opus-5",     # 몸통 — 글의 품질이 곧 결과물
        "figure":  "claude-opus-5",     # SVG 는 좌표를 틀리면 못 쓴다
        "imgprompt": "claude-sonnet-5",  # 프롬프트는 정형이라 소넷으로 충분
    },
    "effort": {
        "outline": "high", "write": "high",
        "figure": "medium", "imgprompt": "medium",
    },
    "budget_usd": {"per_stage": 2.5, "warn_total": 8.0},

    # ── 원고 규약 (5-이론화-에이전트에게.md) — 숫자를 코드에 흩지 않는다 ──
    "manuscript": {
        "box_w": 944,        # 배치 폭 = 960 뷰포트 − UA body{margin:8px} 좌우
        "box_h": 507,        # 한 장이 넘으면 안 되는 높이
        "max_blocks": 6,     # 한 장의 줄 수 상한
        "batch": 8,          # b3-write 한 번에 쓸 장 수
    },

    # ── 이미지 프롬프트 ──
    # ★ `landscape` 는 codex-prompt-img-studio 에서 1536×1024(3:2)로 떨어진다.
    #   gpt-image 네이티브 크기가 1024²·1536×1024·1024×1536 셋뿐이라
    #   **진짜 16:9 는 없다.** 가장 넓은 것이 3:2 다.
    "image": {
        "aspect": "landscape",
        "accent_a": "#2f6b66",   # deep teal — 이 앱의 브랜드
        "accent_b": "#d8b779",   # warm sand — 보색 쪽 강조
        "negative": "text, letters, watermark, logo, low quality, distorted",
    },

    # ★ 사람마다 다른 절대경로. `book2json.config.local.json` 으로 빠진다.
    #   비어 있으면 앱 폴더 옆의 `_contex/` 를 추천한다(`suggest_pdf_dir`).
    "paths": {"pdf_dir": ""},

    "render": {"seed_hex": "#2f6b66"},
}


def suggest_pdf_dir() -> str:
    """새 원고 화면의 「PDF 폴더」 칸에 **미리 채워 둘** 경로.

    ★ 예전엔 이 칸을 빈 채로 두고 placeholder 로 예시 경로만 보여 줬다. 회색 글씨가
      값처럼 보여서, 사람이 다 채웠다고 여기고 다음으로 넘어갔는데 목록이 영영
      안 나왔다(2026-08-14 신고: "새로운 원고 넣으면 아무것도 안 나옵니다").
      **보여 줄 값이면 채워 넣는다.** placeholder 로는 아무것도 시작되지 않는다.
    """
    cfg = load()
    if p := ((cfg.get("paths") or {}).get("pdf_dir") or "").strip():
        return p
    here = APP_DIR / "_contex"
    return str(here) if here.is_dir() else ""


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_cache: Dict[str, Any] | None = None


def load(force: bool = False) -> Dict[str, Any]:
    global _cache
    if _cache is not None and not force:
        return _cache
    file_cfg: Dict[str, Any] = {}
    if CONFIG_PATH.is_file():
        try:
            # ★ utf-8-sig — BOM 을 허용한다. 메모장이나 PowerShell 의
            #   Set-Content -Encoding UTF8 은 BOM 을 붙이는데, 순수 utf-8 로 읽으면
            #   "Unexpected UTF-8 BOM" 으로 통째로 터진다(실제로 겪음).
            file_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{CONFIG_PATH.name} 를 읽지 못했습니다: {e}") from e
    # 내 PC 전용 덮어쓰기 — 있으면 마지막에 이긴다
    local_cfg: Dict[str, Any] = {}
    if LOCAL_PATH.is_file():
        try:
            local_cfg = json.loads(LOCAL_PATH.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{LOCAL_PATH.name} 를 읽지 못했습니다: {e}") from e

    cfg = _deep_merge(_deep_merge(DEFAULTS, file_cfg), local_cfg)
    if p := os.environ.get("PORT") or os.environ.get("BOOK2JSON_PORT"):
        try:
            cfg["port"] = int(p)
        except ValueError:
            pass
    _cache = cfg
    return cfg


# 이 키들은 **사람마다 다른 값**이라 배포본이 아니라 local 파일로 간다
LOCAL_KEYS = {"paths"}


def save(patch: Dict[str, Any]) -> Dict[str, Any]:
    """설정 화면에서 바꾼 값만 덮어쓴다. 파일에 없던 키는 그대로 둔다.

    ★ `paths` 처럼 절대경로가 들어가는 키는 `book2json.config.local.json` 으로 보낸다.
      배포본 설정 파일에 내 PC 경로가 섞이면 동료가 받았을 때 엉뚱한 곳을 가리킨다.
    """
    local_patch = {k: v for k, v in (patch or {}).items() if k in LOCAL_KEYS}
    patch = {k: v for k, v in (patch or {}).items() if k not in LOCAL_KEYS}
    if local_patch:
        cur_local: Dict[str, Any] = {}
        if LOCAL_PATH.is_file():
            try:
                cur_local = json.loads(LOCAL_PATH.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                cur_local = {}
        LOCAL_PATH.write_text(
            json.dumps(_deep_merge(cur_local, local_patch), ensure_ascii=False, indent=2),
            encoding="utf-8")

    cur: Dict[str, Any] = {}
    if CONFIG_PATH.is_file():
        try:
            cur = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            cur = {}
    merged = _deep_merge(cur, patch or {})
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)
    return load(force=True)
