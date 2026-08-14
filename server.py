# -*- coding: utf-8 -*-
"""작가 에이전트 — 로컬 콘솔 서버.

FastAPI + 무빌드 바닐라 SPA. 구조는 `260812-summary-shocase/server.py` 와 같다.
그 앱은 원고를 **받아서** 발표로 만들고, 이 앱은 그 원고를 **써서** 넘긴다.

    단행본 PDF  →  [이 앱]  →  이론 요약 HTML + 대본  →  [발표 쇼케이스]  →  mp4

그림 지시는 **다른 에이전트가 만든다**(2026-08-14). 여기서는 원고와 대본까지다.

산출물은 앱 폴더 밖 형제 폴더에 쌓인다 — core/workspace.py 참고.
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import pipeline  # noqa: F401  — import 만으로 여섯 단계가 STAGES 에 붙는다
from core import activity, book as bk, config, narration as nr, workspace as ws
from core.jobs import get_registry
from pipeline.registry import (STAGES, cached_data, outline_of, read_cache,
                               stage_states, total_cost)

APP_DIR = Path(__file__).resolve().parent
STATIC = APP_DIR / "static"

PDF_EXT = {".pdf"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """서버가 실제로 듣기 시작한 뒤에 브라우저를 연다.

    run.bat 에서 `start ""` 로 먼저 열면 부팅(1~3초)을 앞질러
    ERR_CONNECTION_REFUSED 페이지가 뜬다.
    """
    if os.environ.get("BOOK2JSON_OPEN_BROWSER") == "1":
        port = config.load()["port"]
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    yield


app = FastAPI(title="작가 에이전트", docs_url=None, redoc_url=None, lifespan=lifespan)


# ── 정적 ───────────────────────────────────────────────────────────────────
@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC / "index.html"))


class FreshStatic(StaticFiles):
    """★ 브라우저 캐시를 끈다.

    이 앱은 무빌드다 — 파일명에 해시가 안 붙으니 브라우저가 예전 .js 를 계속
    쓴다. 고쳐 놓고 "안 고쳐졌는데요" 를 겪지 않으려면 이게 맞다. 로컬에서 도는
    앱이라 캐시로 아낄 게 없다.
    """

    def is_not_modified(self, *a, **kw) -> bool:
        return False                      # 304 도 주지 않는다

    async def get_response(self, path: str, scope):
        r = await super().get_response(path, scope)
        r.headers["cache-control"] = "no-store, must-revalidate"
        return r


app.mount("/static", FreshStatic(directory=str(STATIC)), name="static")


# ── 건강 확인 ──────────────────────────────────────────────────────────────
@app.get("/api/health")
def health() -> Dict[str, Any]:
    import shutil

    from llm.claude_provider import find_cli

    exe = find_cli()
    return {
        "ok": True,
        "app_dir": str(APP_DIR),
        "workspace": ws.describe(),
        "claude_cli": str(exe) if exe else None,
        # 실측(b7)은 node + playwright 가 있어야 돈다. 없으면 그 단계만 건너뛴다.
        "node": shutil.which("node"),
        "python": sys.version.split()[0],
    }


@app.get("/api/settings")
def get_settings() -> Dict[str, Any]:
    cfg = dict(config.load())
    cfg["workspace"] = ws.describe()
    # 새 원고 화면이 「PDF 폴더」 칸을 이 값으로 **채워** 둔다(placeholder 아님)
    cfg["suggest_pdf_dir"] = config.suggest_pdf_dir()
    return cfg


@app.post("/api/settings")
def post_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(config.save(patch))
    cfg["workspace"] = ws.describe()
    return cfg


# ── 재료 고르기 ────────────────────────────────────────────────────────────
@app.get("/api/scan")
def scan_pdfs(dir: str) -> Dict[str, Any]:
    """폴더 안의 PDF 목록. **새 원고 화면이 파일을 고르는 자리다.**

    PDF 를 업로드가 아니라 **서버 폴더 경로**로 받는다. 13개 × 평균 9MB 를
    base64 로 올리면 브라우저가 버틴다는 보장이 없고, 무엇보다 책은 이미 이
    PC 에 있다 — 옮길 이유가 없다. 발표 쇼케이스가 화면녹화 폴더를 받는 방식과 같다.
    """
    p = Path((dir or "").strip().strip('"'))
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"폴더가 아닙니다: {p}")
    files = sorted((f for f in p.iterdir()
                    if f.is_file() and f.suffix.lower() in PDF_EXT),
                   key=lambda f: ws.nfc(f.name))
    return {"dir": str(p), "files": [{"path": str(f), "name": f.name,
                                      "mb": round(f.stat().st_size / 1048576, 1)}
                                     for f in files]}


@app.post("/api/upload")
async def upload_pdf(request: Request, name: str) -> Dict[str, Any]:
    """끌어다 놓은 PDF 한 개를 받는다. **본문은 파일 바이트 그대로다.**

    ★ multipart 가 아니라 raw 로 받는다. FastAPI 의 `UploadFile` 은
      `python-multipart` 를 요구하는데, 이 앱은 그 의존성이 없고 얻는 것도 없다 —
      한 요청에 파일 하나면 경계를 파싱할 이유가 없다. 브라우저는 `fetch(body: File)`
      로 그냥 보내면 된다.

    ★ 스트림으로 받아 바로 디스크에 쓴다. 책 한 장이 15MB 쯤이라 메모리에 통째로
      올려도 죽지는 않지만, 여러 개를 한꺼번에 끌어다 놓는 것이 기본 사용법이다.
    """
    d = ws.inbox_dir()
    p = d / ws.safe_name(name)
    # 같은 이름이 이미 있으면 옆에 앉힌다. 덮어쓰면 이미 그 파일로 만든 원고가
    # 다음에 다시 돌 때 다른 책을 읽게 된다.
    if p.exists():
        stem, i = p.stem, 2
        while p.exists():
            p = d / f"{stem} ({i}).pdf"
            i += 1

    tmp = p.with_suffix(".part")
    size = 0
    with tmp.open("wb") as f:
        async for chunk in request.stream():
            size += len(chunk)
            f.write(chunk)
    if size < 1000 or tmp.read_bytes()[:5] != b"%PDF-":
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"PDF 가 아닙니다: {name}")
    tmp.replace(p)
    return {"path": str(p), "name": p.name, "mb": round(size / 1048576, 1)}


@app.get("/api/peek")
def peek_pdf(path: str, head: int = 0, tail: int = 0) -> Dict[str, Any]:
    """PDF 한 개의 앞쪽을 미리 본다 — **앞·뒤로 몇 쪽을 버릴지 정하는 자리.**

    속표지·판권이 몇 장인지는 책마다 다르고, 자동으로 알아내려 들면 틀렸을 때
    본문 첫 쪽이 조용히 사라진다. 사람이 보고 정하게 한다.
    """
    p = Path((path or "").strip().strip('"'))
    if not (p.is_file() and p.suffix.lower() in PDF_EXT):
        raise HTTPException(status_code=400, detail=f"PDF 가 아닙니다: {p}")
    b = bk.read_pdf(p, drop_head=head, drop_tail=tail)
    md, heads = bk.to_markdown(b)
    return {
        "file": b["file"], "pages": len(b["pages"]), "chars": len(md),
        "body_size": b["body_size"], "head_sizes": b["head_sizes"],
        "heads": heads[:60],
        # ★ 목표 길이별 권장 분량. 새 원고 화면이 이걸 표로 깐다 — 사람이 「몇 장」이
        #   아니라 **「몇 분짜리」**로 고르게 하려는 것이다(2026-08-14: 19장이
        #   5분 30초로 나온 뒤). 계산은 core/narration.py 한 곳에서만 한다.
        "length_options": nr.options(len(md)),
        "sample": [{"no": pg["no"],
                    "text": " ".join(bk.join_lines(
                        [" ".join(x["lines"]) for x in pg["body"]]))[:400]}
                   for pg in b["pages"][:3]],
    }


# ── 프로젝트 ───────────────────────────────────────────────────────────────
class ProjectIn(BaseModel):
    title: Optional[str] = None        # 이 장의 이름 — 원고의 h1 이 된다
    book: Optional[str] = None         # 책 이름
    pdfs: List[str] = []               # 서버 안의 절대 경로
    id_prefix: Optional[str] = None    # 이름표 앞머리 — `sam` → `sam-03`
    target_min: int = nr.DEFAULT_MIN   # 목표 영상 길이(분). **여기서 장 수가 나온다**
    slide_budget: int = 40
    drop_head: int = 0
    drop_tail: int = 0
    tone: Optional[str] = None


@app.get("/api/projects")
def list_projects() -> List[Dict[str, Any]]:
    return ws.list_projects()


def _find(pid: int) -> Dict[str, Any]:
    for p in ws.list_projects():
        if p["id"] == pid:
            doc = ws.load_project(pid, p["slug"])
            doc.setdefault("slug", p["slug"])
            return doc
    raise HTTPException(status_code=404, detail="없는 원고입니다")


@app.get("/api/projects/{pid}")
def get_project(pid: int) -> Dict[str, Any]:
    return _find(pid)


@app.post("/api/projects")
def create_project(body: ProjectIn) -> Dict[str, Any]:
    paths = [Path(x.strip().strip('"')) for x in body.pdfs if (x or "").strip()]
    good = [p for p in paths if p.is_file() and p.suffix.lower() in PDF_EXT]
    if not good:
        raise HTTPException(status_code=400, detail="읽을 PDF 를 하나는 넣어야 합니다")

    # 제목이 없으면 **첫 PDF 이름에서 딴다.** 「새뮤얼슨의경제학-5부 19장.pdf」
    # 처럼 사람이 이미 이름을 잘 지어 두었으므로, 빈 칸을 강요할 이유가 없다.
    title = (body.title or "").strip() or good[0].stem
    prefix = (body.id_prefix or "").strip().lower() or (ws.ascii_slug(title, 6) or "bk")

    pid = ws.next_pid()
    slug = ws.slug(title)
    doc = {
        "id": pid, "slug": slug, "title": title,
        "book": (body.book or "").strip(),
        "pdfs": [str(p) for p in good],
        "id_prefix": prefix,
        # ★ 길이가 목적이고 장 수는 그 결과다. 목표를 프로젝트에 적어 두면 목차를
        #   세울 때도, 다 되고 나서 몇 분짜리인지 셀 때도 같은 수를 본다.
        "target_min": max(1, int(body.target_min or nr.DEFAULT_MIN)),
        # ★ 0 은 「비워 둠」이다 — 장 나누기(b2)가 그때 원문을 보고 목표 길이에서
        #   뽑는다. 여러 PDF 를 한꺼번에 고른 경우가 그렇다: 장마다 두께가 달라서
        #   첫 장의 예산을 나머지에 물려주면 안 된다.
        "slide_budget": max(0, int(body.slide_budget or 0)),
        "drop_head": max(0, int(body.drop_head or 0)),
        "drop_tail": max(0, int(body.drop_tail or 0)),
        "tone": (body.tone or "").strip(),
        "outline_rev": 0,
        "created_at": ws._now(),
    }
    ws.save_project(pid, slug, doc)
    return doc


@app.delete("/api/projects/{pid}")
def hide_project(pid: int) -> Dict[str, Any]:
    doc = _find(pid)
    return {"ok": True, "dir": ws.hide_project(pid, doc["slug"]),
            "note": "목록에서 감췄습니다. 폴더는 그대로 있으니 직접 지우세요."}


@app.get("/api/projects/{pid}/stages")
def get_stages(pid: int) -> Dict[str, Any]:
    doc = _find(pid)
    return {"stages": stage_states(pid, doc["slug"], doc),
            "cost_usd": total_cost(pid, doc["slug"])}


# ── 목표 길이 ──────────────────────────────────────────────────────────────
def _length_state(pid: int, doc: Dict[str, Any]) -> Dict[str, Any]:
    """이 원고가 **몇 분짜리를 노리고 있고, 지금 몇 분짜리인가.**

    ★ 지금 길이는 조립(b6)이 세어 둔 값을 그대로 읽는다. 여기서 다시 세면 조립한
      원고와 화면이 어긋나는 순간이 온다 — 세는 자리는 하나여야 한다.
    """
    slug = doc["slug"]
    src = cached_data(pid, slug, "b1-pdf") or {}
    want = nr.plan_of(doc, int(src.get("chars") or 0))
    built = (cached_data(pid, slug, "b6-assemble") or {}).get("length")
    # 아직 조립 전이면 목차의 say 로라도 지금 길이를 말해 준다 — 몸통을 쓰기 전에
    # 「이대로면 6분짜리」를 알아야 목차 단계에서 고칠 수 있다.
    if not built:
        says = [s.get("say") or "" for s in (outline_of(pid, slug).get("slides") or [])]
        built = nr.verdict(nr.count_all(says), want) if says else None
    return {"target_min": want["minutes"], "plan": want, "now": built,
            "source_chars": int(src.get("chars") or 0),
            "options": nr.options(int(src.get("chars") or 0))}


@app.get("/api/projects/{pid}/length")
def get_length(pid: int) -> Dict[str, Any]:
    return _length_state(pid, _find(pid))


class LengthIn(BaseModel):
    target_min: int


@app.post("/api/projects/{pid}/length")
def post_length(pid: int, body: LengthIn) -> Dict[str, Any]:
    """목표 길이를 바꾼다 — **장 예산도 같이 따라간다.**

    이미 만든 원고도 여기서 15분으로 올릴 수 있다. 목차(b2)가 `target_min` 을 읽으므로
    바꾸는 즉시 그 단계가 낡은 것으로 잡히고, 다시 돌리면 그 길이에 맞는 장 수와
    말 길이로 다시 짜인다.
    """
    doc = _find(pid)
    src = cached_data(pid, doc["slug"], "b1-pdf") or {}
    chars = int(src.get("chars") or 0)
    p = nr.plan(chars, body.target_min)
    doc["target_min"] = p["minutes"]
    # 아직 책을 안 읽었으면 장 예산은 **비워 둔다.** 원문을 모르는 채로 뽑은 수를
    # 적어 두면 그 수가 진짜 값인 척 남는다.
    doc["slide_budget"] = p["slides"] if chars else 0
    ws.save_project(pid, doc["slug"], doc)
    return _length_state(pid, doc)


@app.get("/api/projects/{pid}/activity")
def get_activity(pid: int) -> Dict[str, Any]:
    doc = _find(pid)
    return activity.build(pid, doc["slug"], doc)


# ── 목차 ───────────────────────────────────────────────────────────────────
@app.get("/api/projects/{pid}/outline")
def get_outline(pid: int) -> Dict[str, Any]:
    """**손편집을 얹은** 목차. 화면과 원고가 같은 것을 보게 하는 유일한 출처다."""
    doc = _find(pid)
    o = outline_of(pid, doc["slug"])
    draft = (cached_data(pid, doc["slug"], "b3-write") or {}).get("slides") or {}
    figs = (cached_data(pid, doc["slug"], "b4-figure") or {}).get("figures") or {}
    check = {v["id"]: v for v in
             ((cached_data(pid, doc["slug"], "b7-check") or {}).get("violations") or [])}

    slides = []
    for s in o.get("slides") or []:
        did = s["data_id"]
        body = draft.get(did) or {}
        slides.append({
            **s,
            "blocks": body.get("blocks") or [],
            "lines": body.get("lines") or 0,
            "has_svg": bool(figs.get(did)),
            "say_chars": nr.count(s.get("say") or ""),
            "flags": (check.get(did) or {}).get("flags") or [],
            "height": (check.get(did) or {}).get("height"),
        })
    return {"ready": bool(slides), "title": o.get("title") or doc.get("title"),
            "groups": o.get("groups") or [], "slides": slides,
            "dropped": o.get("dropped") or [], "rev": doc.get("outline_rev") or 0}


class OverrideIn(BaseModel):
    patch: Dict[str, Any]


@app.post("/api/projects/{pid}/overrides")
def post_overrides(pid: int, body: OverrideIn) -> Dict[str, Any]:
    """손편집 저장(sparse deep-merge). 스테이지를 다시 돌려도 이건 살아남는다."""
    doc = _find(pid)
    cur = ws.load_overrides(pid, doc["slug"])

    def merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(a)
        for k, v in (b or {}).items():
            out[k] = (merge(out.get(k, {}), v)
                      if isinstance(v, dict) and isinstance(out.get(k), dict) else v)
        return out

    ws.save_overrides(pid, doc["slug"], merge(cur, body.patch))

    # ★ 손편집도 **뒤 단계를 낡게 만든다.** 오버라이드 파일은 스테이지 해시에 안
    #   들어가서, 세는 값 하나를 프로젝트에 두고 b3·b6 이 그걸 읽게 한다. 안 그러면
    #   제목을 고쳐 놓고도 "할 일 없음" 이 떠서, 고친 채로 내보내게 된다.
    doc["outline_rev"] = int(doc.get("outline_rev") or 0) + 1
    ws.save_project(pid, doc["slug"], doc)
    return {"ok": True, "outline_rev": doc["outline_rev"]}


# ── 이미지 프롬프트 — **이 앱에서 뺐다** ───────────────────────────────────
#
# 2026-08-14 결정: 그림 지시는 다른 에이전트가 만든다. 여기 있던 두 엔드포인트
# (`GET /api/projects/{pid}/prompts` · `POST …/prompts/{data_id}`)와 그것을 쓰던
# 화면(`static/js/image.js`)이 같이 빠졌다. 원장을 다루던 코드는 `core/ledger.py`
# 에 그대로 있다 — 되살릴 때 이 자리에 다시 붙이면 된다(git 이력에 통째로 있다).


# ── 원고 미리보기 · 내려받기 ───────────────────────────────────────────────
@app.get("/preview/{pid}")
def preview(pid: int):
    """조립된 원고를 그대로 띄운다. 화면의 미리보기 틀이 이걸 iframe 으로 문다."""
    doc = _find(pid)
    f = Path((cached_data(pid, doc["slug"], "b6-assemble") or {}).get("file") or "")
    if not f.is_file():
        return PlainTextResponse("아직 원고가 없습니다. 조립(5번)을 먼저 돌리세요",
                                 status_code=404)
    return FileResponse(str(f), media_type="text/html; charset=utf-8",
                        headers={"cache-control": "no-store"})


@app.get("/api/projects/{pid}/files")
def list_files(pid: int) -> Dict[str, Any]:
    doc = _find(pid)
    d = ws.step_dir(pid, doc["slug"], "export", create=False)
    if not d.is_dir():
        return {"dir": str(d), "files": [], "bak": []}

    def rows(folder: Path) -> List[Dict[str, Any]]:
        return [{"name": f.name, "kb": round(f.stat().st_size / 1024)}
                for f in sorted(folder.iterdir()) if f.is_file()] if folder.is_dir() else []

    # 넘기는 것과 안 넘기는 것을 **폴더로 가른다.** 위 칸에 있는 것이 곧 넘길 것이다.
    return {"dir": str(d), "files": rows(d), "bak": rows(d / "bak")}


@app.get("/api/projects/{pid}/files/{name}")
def get_file(pid: int, name: str, bak: bool = False):
    doc = _find(pid)
    d = ws.step_dir(pid, doc["slug"], "export", create=False)
    f = ws.safe_child(d / "bak" if bak else d, name)
    if not f:
        raise HTTPException(status_code=404, detail="없는 파일입니다")
    return FileResponse(str(f), filename=f.name)


# ── 실행 ───────────────────────────────────────────────────────────────────
@app.post("/api/projects/{pid}/stages/{stage}/run")
def run_stage(pid: int, stage: str, force: bool = False) -> Dict[str, Any]:
    doc = _find(pid)
    spec = STAGES.get(stage)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"모르는 단계: {stage}")
    if spec.run is None:
        raise HTTPException(status_code=501, detail=f"{spec.label} 은 아직 구현 전입니다")

    reg = get_registry()
    try:
        job = reg.start(
            project_id=pid, stage=stage, label=spec.label,
            work=lambda j: spec.run(j, pid, doc["slug"], doc, force=force),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return job.to_dict()


@app.get("/api/jobs/running")
def job_running() -> Dict[str, Any]:
    j = get_registry().any_running()
    return j.to_dict() if j else {"running": False}


@app.get("/api/jobs/{job_id}")
def job_get(job_id: str) -> Dict[str, Any]:
    j = get_registry().get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="없는 잡입니다")
    return j.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str) -> Dict[str, Any]:
    j = get_registry().get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="없는 잡입니다")
    j.cancel()
    return j.to_dict()


# ── 오류 봉투 ──────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
def on_error(_req, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500,
                        content={"detail": f"{type(exc).__name__}: {exc}"})
