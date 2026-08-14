# -*- coding: utf-8 -*-
"""산출물 아카이브 — 파일시스템이 source of truth.

**경로를 조립하는 유일한 곳.** 다른 모듈은 여기서만 경로를 받아 간다.
구조는 `260812-summary-shocase/core/workspace.py` 그대로다. 단계 이름만 갈았다.

산출물은 앱 폴더 **밖**, 형제 폴더에 쌓인다:

    D:\\00work\\260814-book2json\\        ← 앱 (git)
    D:\\00work\\book2json-out-260814\\    ← 산출물 (BOOK2JSON_WORKSPACE 로 재지정)

이렇게 두는 이유:
  - `git clean` 이나 레포 재클론이 산출물을 지울 수 없다.
  - 백업·이관이 폴더 하나 복사로 끝난다.
  - 앱을 지우고 다시 받아도 써 둔 원고가 그대로 남는다.

폴더는 **파이프라인 단계와 1:1** 이다. 어느 단계 산출물인지 경로만 봐도 알아야 하고,
한 단계를 다시 돌려도 다른 단계 결과가 섞이지 않는다.

    book2json-out-260814/
      01_새뮤얼슨-19장/            ← 프로젝트 (NN_slug)
        project.json
        01_원문/     pages.json · 본문.md · <원본>.pdf(복사본 아님, 경로만 기록)
        02_목차/     outline.json · outline.overrides.json
        03_원고/     draft.json
        04_그림/     figures.json
        09_이미지/   원장.json          ← data-id 로 쌓이는 프롬프트 원장
        10_내보내기/ <장>_원고.html · 이미지프롬프트.json
                     이미지프롬프트_부족분.json · 이름바꾸기.txt
        _cache/      스테이지 캐시 (input_hash · cost · status)
        _logs/
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APP_DIR = Path(__file__).resolve().parent.parent

# 기본값은 앱 폴더의 **형제**. showcase 의 SHOWCASE_WORKSPACE 와 같은 규약.
ROOT = Path(
    os.environ.get("BOOK2JSON_WORKSPACE")
    or (APP_DIR.parent / f"book2json-out-{APP_DIR.name.split('-')[0]}")
)

# 단계 키 → (폴더명, 사람이 읽는 이름)
# ★ 폴더명은 바꾸지 않는다. 이미 만든 프로젝트의 산출물이 미아가 된다.
STEPS: Dict[str, Tuple[str, str]] = {
    "source":  ("01_원문", "책에서 뽑은 글"),
    "outline": ("02_목차", "장 나누기"),
    "draft":   ("03_원고", "장별 몸통"),
    "figure":  ("04_그림", "인라인 SVG"),
    "images":  ("09_이미지", "이미지 프롬프트"),
    "export":  ("10_내보내기", "내보내기"),
}

CACHE = "_cache"
LOGS = "_logs"

F_PROJECT = "project.json"
# ★ 목차는 사람이 고친다(장 합치기·쪼개기·제목 손질). 원본과 손편집을 **따로** 둔다 —
#   b2-outline 을 다시 돌려도 손편집이 살아남아야 하기 때문이다.
F_OUTLINE = "outline.json"
F_OVERRIDES = "outline.overrides.json"
F_LEDGER = "원장.json"

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_ASCII_BAD = re.compile(r"[^a-z0-9-]+")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def nfc(s: str) -> str:
    """macOS 에서 온 파일명은 NFD 라 `==` 매칭이 실패한다. 비교 전 항상 통과시킨다."""
    return unicodedata.normalize("NFC", s or "")


def slug(name: str, limit: int = 40) -> str:
    """폴더명으로 안전한 이름. 한글은 그대로 둔다(사람이 폴더를 직접 여니까)."""
    s = _BAD.sub("", nfc(name).strip())
    s = re.sub(r"\s+", "-", s).strip(". -")
    return (s or "project")[:limit]


def ascii_slug(name: str, limit: int = 40) -> str:
    """파생 **파일명**용. 한글 파일명이 ffmpeg·URL·zip 을 깨는 것을 원천 차단한다.

    한글은 JSON 값(`source_label`)에만 살고, 디스크의 파생물은 전부 ascii 다.
    """
    s = _ASCII_BAD.sub("-", nfc(name).strip().lower()).strip("-")
    return (s or "item")[:limit]


# ── 경로 ──────────────────────────────────────────────────────────────────
def project_dir(pid: int, slug_name: str, *, create: bool = True) -> Path:
    """프로젝트 폴더. 같은 pid 폴더가 이미 있으면(이름이 바뀌었어도) 그것을 쓴다."""
    ROOT.mkdir(parents=True, exist_ok=True)
    prefix = f"{int(pid):02d}_"
    for d in sorted(ROOT.iterdir()):
        if d.is_dir() and d.name.startswith(prefix):
            return d
    p = ROOT / f"{prefix}{slug(slug_name)}"
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def step_dir(pid: int, slug_name: str, step: str, *, create: bool = True) -> Path:
    p = project_dir(pid, slug_name, create=create) / STEPS[step][0]
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def step_label(step: str) -> str:
    return STEPS[step][1]


def sub_dir(pid: int, slug_name: str, step: str, which: str, *, create: bool = True) -> Path:
    d = step_dir(pid, slug_name, step, create=create) / which
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir(pid: int, slug_name: str, *, create: bool = True) -> Path:
    d = project_dir(pid, slug_name, create=create) / CACHE
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir(pid: int, slug_name: str, *, create: bool = True) -> Path:
    d = project_dir(pid, slug_name, create=create) / LOGS
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


# ── 읽기/쓰기 ─────────────────────────────────────────────────────────────
def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def write_json(p: Path, obj) -> Path:
    """원자적 쓰기. 중간에 죽어도 반쪽짜리 JSON 이 남지 않는다."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def write_text(p: Path, text: str, *, bom: bool = False) -> Path:
    """BOM 없는 utf-8 이 기본. csv 만 엑셀 때문에 BOM 을 붙인다."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8-sig" if bom else "utf-8")
    tmp.replace(p)
    return p


# ── 프로젝트 메타 ──────────────────────────────────────────────────────────
def project_path(pid: int, slug_name: str, *, create: bool = False) -> Path:
    return project_dir(pid, slug_name, create=create) / F_PROJECT


def load_project(pid: int, slug_name: str) -> Dict[str, Any]:
    return read_json(project_path(pid, slug_name), {}) or {}


def save_project(pid: int, slug_name: str, doc: Dict[str, Any]) -> Path:
    doc = dict(doc or {})
    doc["id"] = int(pid)
    doc["updated_at"] = _now()
    return write_json(project_path(pid, slug_name, create=True), doc)


# ── 목차 · 원장 ────────────────────────────────────────────────────────────
def outline_path(pid: int, slug_name: str, *, create: bool = False) -> Path:
    return step_dir(pid, slug_name, "outline", create=create) / F_OUTLINE


def overrides_path(pid: int, slug_name: str, *, create: bool = False) -> Path:
    return step_dir(pid, slug_name, "outline", create=create) / F_OVERRIDES


def ledger_path(pid: int, slug_name: str, *, create: bool = False) -> Path:
    """이미지 프롬프트 원장. **data-id 가 키다** — 슬라이드 번호가 아니다.

    번호는 앞에 장 하나만 끼어들어도 전부 밀린다(`005.png` 가 남의 그림이 된다).
    이름표는 안 밀린다. 그래서 프롬프트는 이름표에 매달고, 번호는 내보낼 때만 매긴다.
    """
    return step_dir(pid, slug_name, "images", create=create) / F_LEDGER


def load_ledger(pid: int, slug_name: str) -> Dict[str, Any]:
    return read_json(ledger_path(pid, slug_name), {}) or {}


def save_ledger(pid: int, slug_name: str, doc: Dict[str, Any]) -> Path:
    return write_json(ledger_path(pid, slug_name, create=True), doc)


def load_overrides(pid: int, slug_name: str) -> Dict[str, Any]:
    return read_json(overrides_path(pid, slug_name), {}) or {}


def save_overrides(pid: int, slug_name: str, doc: Dict[str, Any]) -> Path:
    """손편집 패치 — **내용이 같으면 쓰지 않고, 다르면 .bak 을 남긴다.**

    이 파일은 콘솔 UI 와 사람이 함께 고친다. 그냥 덮어쓰면 손으로 다듬은 제목을
    날린다. showcase 의 덱 오버라이드가 같은 이유로 같은 규칙을 쓴다.
    """
    p = overrides_path(pid, slug_name, create=True)
    new = json.dumps(doc or {}, ensure_ascii=False, indent=2)
    if p.is_file():
        old = p.read_text(encoding="utf-8")
        if old == new:
            return p
        p.with_suffix(p.suffix + ".bak").write_text(old, encoding="utf-8")
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(new, encoding="utf-8")
    tmp.replace(p)
    return p


# ── 다운로드 (경로 탈출 차단) ──────────────────────────────────────────────
def safe_child(base: Path, filename: str) -> Optional[Path]:
    """`base` 밖으로 나가는 경로를 거부한다. 다운로드 엔드포인트 전용."""
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    p = (base / filename).resolve()
    try:
        p.relative_to(base.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


# ── 목록 ───────────────────────────────────────────────────────────────────
def list_projects() -> List[Dict[str, Any]]:
    """workspace 안의 프로젝트 목록. **파일이 source of truth** — DB 행이 없어도 보인다."""
    out: List[Dict[str, Any]] = []
    if not ROOT.is_dir():
        return out
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir():
            continue
        m = re.match(r"^(\d+)_", d.name)
        if not m:
            continue
        if (d / F_HIDDEN).exists():      # 감춘 것 — 폴더는 그대로 있다
            continue
        meta = read_json(d / F_PROJECT, {}) or {}
        out.append({
            "id": int(meta.get("id") or m.group(1)),
            "slug": meta.get("slug") or d.name[len(m.group(0)):],
            "title": meta.get("title") or d.name[len(m.group(0)):],
            "dir": str(d),
            "slides": int(meta.get("slide_count") or 0),
            "updated_at": meta.get("updated_at"),
        })
    return out


def all_pids() -> List[int]:
    """폴더에 있는 **모든** 번호. 감춘 것도 센다."""
    out: List[int] = []
    if not ROOT.is_dir():
        return out
    for d in ROOT.iterdir():
        m = re.match(r"^(\d+)_", d.name) if d.is_dir() else None
        if m:
            out.append(int(m.group(1)))
    return out


def next_pid() -> int:
    """★ **감춘 폴더도 번호를 차지한다.**

    예전엔 보이는 목록에서만 최댓값을 셌다. 04 를 감춰 두면 다음 번호가 다시
    04 가 되고, 새 프로젝트가 감춰진 폴더 안으로 들어간다 — 만들자마자
    "프로젝트를 찾을 수 없습니다" 가 뜨고 폼이 초기화된다. 실제로 그랬다.
    폴더 이름의 번호를 직접 센다.
    """
    return max(all_pids(), default=0) + 1


F_HIDDEN = "_감춤"


def hide_project(pid: int, slug_name: str) -> str:
    """★ **지우지 않는다.** 목록에서 감추고, 폴더 경로를 돌려준다.

    산출물에는 몇 시간짜리 Claude 호출 결과와 손으로 고친 원고가 들어 있다.
    그것을 버튼 하나로 지우는 코드는 두지 않는다 — 잘못 눌렀을 때 되돌릴 방법이
    없기 때문이다. 앱은 시야에서 치우기만 하고, 폴더는 사람이 탐색기에서 직접
    지운다. 마음이 바뀌면 이 표시 파일만 지우면 목록에 다시 나온다.
    """
    d = project_dir(pid, slug_name, create=False)
    if d.is_dir():
        (d / F_HIDDEN).write_text(
            "이 파일이 있으면 앱 목록에 나오지 않습니다.\n"
            "다시 보이게 하려면 이 파일을 지우세요.\n", encoding="utf-8")
    return str(d)


def describe() -> Dict[str, Any]:
    """설정 화면에 보여줄 현재 워크스페이스 정보."""
    return {
        "app_dir": str(APP_DIR),
        "root": str(ROOT),
        "exists": ROOT.is_dir(),
        "from_env": bool(os.environ.get("BOOK2JSON_WORKSPACE")),
        "projects": len(list_projects()),
    }
