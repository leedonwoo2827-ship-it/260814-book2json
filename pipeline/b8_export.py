# -*- coding: utf-8 -*-
"""B8 내보내기 — **원고 한 장과 그림 지시 세 장.**

    <slug>_원고.html            발표 쇼케이스의 「참고 자료」 칸에 넣을 것
    이미지프롬프트.json          이미지 스튜디오에 통째로 넣을 것
    이미지프롬프트_부족분.json    새로 생겼거나 몸통이 바뀐 장만
    이름바꾸기.txt               번호가 밀린 그림을 옮길 목록

★ **부족분과 이름 바꾸기가 이 단계의 존재 이유다.**
  원고를 눈으로 보고 고친 뒤 그림을 만드는 순서인데, 그림 파일 이름은 슬라이드
  번호다(`005.png`). 앞에 장이 하나 끼어들면 번호가 전부 밀려서 이미 그린 그림이
  통째로 남의 장 것이 된다. 원장(`core/ledger.py`)이 이름표로 기억하고 있으므로,
  여기서 **무엇이 몇 번에서 몇 번으로 갔는지**를 표로 낼 수 있다.

★ JSON 모양은 `codex-prompt-img-studio` 가 읽는 그대로다. 그 앱이 실제로 필요한
  것은 `prompts[].prompt` 하나뿐이고 나머지는 안 읽지만(`services/batch_jobs.py`
  의 `normalize_payload`), 받은 샘플과 같은 아홉 칸을 다 채운다 — 사람이 두 파일을
  나란히 놓고 볼 것이고, 그 샘플이 사실상의 표준이다.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core import config, ledger as lg, workspace as ws
from pipeline.registry import STAGES, cached_data, write_cache

FILE_NAMING = ("생성한 이미지는 images/ 폴더에 '슬라이드번호'로 저장하세요. "
               "예: 003.png → 3번 슬라이드. 파일명 앞 숫자만 맞으면 되고 "
               "확장자·뒤 설명은 자유입니다(003_저축함수.png).")


def bundle(*, deck: str, cfg: Dict[str, Any], rows: List[Dict[str, Any]],
           deck_slides: int) -> Dict[str, Any]:
    """이미지 스튜디오가 먹는 봉투 하나."""
    img = cfg["image"]
    return {
        "deck": deck,
        # ★ `style_hint` 는 각 `prompt` 에 이미 박혀 있다. 여기 한 번 더 두는 것은
        #   사람이 읽으라고다 — 스튜디오는 앞 40자로 중복을 걸러 다시 안 붙인다.
        "style_hint": rows[0]["prompt"].split(". ", 1)[-1].rsplit(". No text", 1)[0]
                      if rows else "",
        # landscape → 1536×1024 (3:2). gpt-image 의 네이티브 크기가 정사각·3:2·2:3
        # 셋뿐이라 **진짜 16:9 는 없다.** 가장 넓은 것이 이것이다.
        "aspect": img["aspect"],
        "target_box": "wide horizontal panel (3:2), may be cropped to 16:9 for video",
        "count": len(rows),
        "deck_slides": deck_slides,
        "photos_found": 0,
        "file_naming": FILE_NAMING,
        "prompts": rows,
    }


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["b8-export"]
    cfg = config.load()
    built = cached_data(pid, slug, "b6-assemble") or {}
    order: List[str] = built.get("order") or []
    if not order:
        raise RuntimeError("원고 조립(b6-assemble)을 먼저 돌리세요")

    book = ws.load_ledger(pid, slug)
    by_id: Dict[str, Any] = book.get("by_id") or {}

    # ★ 번호는 **여기서 처음 매긴다.** 원장은 이름표로만 기억한다.
    #   1번은 표지라 원고의 첫 장이 2번이다 — 발표 쇼케이스가 세는 번호와 같다.
    plan = lg.number(book, order, start=2)
    n_of, renames, fresh = plan["n_of"], plan["renames"], plan["fresh"]
    # ★ 부족분은 **새 장 + 프롬프트가 다시 만들어진 장**이다. 번호만 밀린 장은
    #   여기 안 들어간다 — 그건 이름만 바꾸면 되는 장이고, 다시 그리라고 하면
    #   이 앱이 막으려던 바로 그 낭비가 된다.
    need = set(fresh) | set(plan["dirty"])

    rows: List[Dict[str, Any]] = []
    gap: List[Dict[str, Any]] = []
    miss: List[str] = []
    for did in order:
        e = by_id.get(did) or {}
        prompt = (e.get("prompt") or "").strip()
        if not prompt:
            miss.append(did)
            continue
        row = {
            "n": n_of[did],
            "title": e.get("title") or "",
            "type": e.get("type") or "photo",
            "level": e.get("level") or "이해",
            "prompt": prompt,
            "negative": cfg["image"]["negative"],
            "keywords": e.get("keywords") or [],
            "place": True,
            # ★ 규격 밖의 칸이다. 스튜디오는 안 읽고 사람이 읽는다 — 번호만 있는
            #   JSON 을 나중에 열면 어느 장인지 알 방법이 없다.
            "data_id": did,
        }
        rows.append(row)
        if did in need:
            gap.append(row)

    if not rows:
        raise RuntimeError("그림 지시문이 하나도 없습니다. 이미지 프롬프트(b5)를 먼저 돌리세요")

    deck = f"{project.get('book') or ''} · {project.get('title') or slug}".strip(" ·")
    d = ws.step_dir(pid, slug, "export")
    total = len(order) + 1                          # +1 = 표지

    p_all = ws.write_json(d / "이미지프롬프트.json",
                          bundle(deck=deck, cfg=cfg, rows=rows, deck_slides=total))

    # ★ 없으면 **지운다.** 지난번 부족분이 그대로 남아 있으면 사람이 그것을 집어
    #   이미 그린 그림을 다시 그린다 — 이 앱이 막으려던 바로 그 일이다.
    #   "이번엔 부족분이 없다" 는 말은 파일이 없는 것으로만 확실히 전해진다.
    p_gap = None
    gap_file = d / "이미지프롬프트_부족분.json"
    if gap:
        p_gap = ws.write_json(gap_file, bundle(deck=deck + " (부족분)", cfg=cfg,
                                               rows=gap, deck_slides=total))
    else:
        gap_file.unlink(missing_ok=True)

    # 이름 바꾸기 표 — 사람이 탐색기에서 보고 옮긴다. 자동으로 옮기지 않는다:
    # 그림 폴더는 이 앱 밖(이미지 스튜디오 쪽)에 있고, 남의 폴더를 건드리는 코드는
    # 잘못 돌았을 때 되돌릴 방법이 없다.
    p_ren = None
    ren_file = d / "이름바꾸기.txt"
    if renames:
        lines = ["번호가 밀린 그림입니다. 이미지 폴더에서 아래대로 이름을 바꾸세요.",
                 "★ 이 장들은 **내용이 그대로**입니다 — 다시 그리지 말고 이름만 바꾸세요.",
                 "★ 뒤에서부터 바꾸세요 — 앞에서부터 하면 아직 안 바꾼 파일을 덮어씁니다.",
                 ""]
        for old, new, did in sorted(renames, key=lambda r: -r[1]):
            title = (by_id.get(did) or {}).get("title") or ""
            lines.append(f"{old:03d}.png  →  {new:03d}.png    {did}  {title}")
        p_ren = ws.write_text(ren_file, "\n".join(lines) + "\n")
    else:
        ren_file.unlink(missing_ok=True)

    # ★ 파일을 다 쓴 **뒤에** 번호를 원장에 찍는다. 쓰다 실패했는데 번호를 찍으면
    #   다음 내보내기가 「바뀐 것 없음」 이라 말하고 이름 바꾸기 표가 영영 안 나온다.
    ws.save_ledger(pid, slug, lg.stamp(book, n_of))

    job.add_log(f"원고: {built.get('file')}")
    job.add_log(f"프롬프트 {len(rows)}개 (전체 {len(order)}장 중) → {p_all}")
    if p_gap:
        job.add_log(f"부족분 {len(gap)}개 (새 장 {len(fresh)}개 · 몸통이 바뀐 장 "
                    f"{len(plan['dirty'])}개) → {p_gap}")
    else:
        job.add_log("부족분 없음 — 지난번에 만든 그림을 그대로 쓰면 됩니다")
    if p_ren:
        job.add_log(f"번호만 밀린 그림 {len(renames)}개 → {p_ren}")
        job.add_log("★ 이 장들은 내용이 그대로입니다. 다시 그리지 말고 이름만 바꾸세요")

    warn = [f"그림 지시문이 없는 장 {len(miss)}개"] if miss else []
    if miss:
        job.add_log(f"지시문이 없어 뺀 장: {', '.join(miss[:10])}")

    return write_cache(pid, slug, "b8-export",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"dir": str(d), "count": len(rows), "gap": len(gap),
                             "renames": [[o, n, i] for o, n, i in renames],
                             "fresh": fresh, "missing": miss,
                             "files": [str(x) for x in (p_all, p_gap, p_ren) if x]},
                       code_version=stage.code_version,
                       status="degraded" if warn else "ok", warnings=warn)


STAGES["b8-export"].run = run
