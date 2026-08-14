# -*- coding: utf-8 -*-
"""스테이지 모듈을 **불러오기만 해도** 레지스트리에 붙게 한다.

각 모듈 맨 끝의 `STAGES["b1-pdf"].run = run` 이 그 일을 한다. 서버가 이 꾸러미를
import 하면 여섯 단계가 전부 실행 가능해진다 — 어느 것 하나를 빼먹으면 화면에서
그 단계만 「아직 구현 전」 으로 회색이 된다.

★ 순서대로 적는다. 위에서 아래가 곧 파이프라인 순서다.

★ **`b5_imgprompt` 와 `b8_export` 는 여기 없다.** 2026-08-14 에 이미지 프롬프트를
  이 앱에서 뺐다 — 그림 지시는 **다른 에이전트가 만든다.** 파일은 지우지 않고
  파이프라인에서만 뗐다(`pipeline/registry.py` 참고). 다시 넣으려면 두 이름을
  아래 목록과 registry 의 `_DEFS` 에 되돌리면 된다.
"""
from pipeline import (          # noqa: F401  (import 자체가 목적이다)
    b1_pdf, b2_outline, b3_write, b4_figure, b6_assemble, b7_check,
)
