# 책 원고 에이전트 (260814-book2json)

단행본 PDF 를 넣으면 **발표 쇼케이스가 그대로 먹는 이론 요약 HTML 한 장**과
**가로형 이미지 프롬프트 JSON** 이 나온다.

```
단행본 PDF  →  [이 앱 · 5187]  →  <장>_원고.html      →  [발표 쇼케이스 · 5178]  →  mp4
                              →  이미지프롬프트.json  →  [이미지 스튜디오]        →  png
```

이 앱은 사슬의 가운데 토막이다. 혼자 쓰이지 않으므로, 나가는 파일마다 **받는 쪽**이
정해져 있다. `#/export` 화면이 파일마다 그것을 적어 준다.

## 무엇을 지키는가

계약서는 `260812-summary-shocase/_new-context/5-이론화-에이전트에게.md` 다.
그 편지는 사람에게 "이렇게 써 주세요" 라고 부탁한 것인데, 이 앱은 부탁이 아니라
**구조로 못 박는다** — 조립기가 낼 수 있는 모양이 하나뿐이라 어길 방법이 없다.

- `<body>` 바로 밑이 평평하다. 감싸는 `<div>` 를 아예 안 만든다
- `h1` 표지 · `h2` 묶음 · **`h3` 하나 = 슬라이드 한 판**
- 한 판은 **944 × 507 px** 안에, **여섯 줄 이내**
- `<li>` 하나에 한 생각. 따로 나타나야 하는 생각은 따로 된 요소로
- `vh`/`vw` · `@import` · 외부 파일 참조 · `position:fixed` 없음
- 그림은 인라인 `<svg viewBox>` 로만

여기에 이 앱이 더하는 것 셋:

| | |
|---|---|
| `data-id` | **안 바뀌는 이름표.** 그림 파일이 여기 매달린다 |
| `data-say` | 그 장에서 말할 한두 문장. 줄 등장 시각이 정확해진다 |
| `data-img` | 그 장의 가로형 이미지 프롬프트 |

그리고 **장마다 인라인 SVG 하나 또는 표 하나**가 들어간다. 줄글만 늘어놓는 화면을
만들지 않는 것이 이 원고의 목적이다.

## 왜 번호가 아니라 이름표인가 — 이 앱의 뼈대

원고를 눈으로 보고 고친 **뒤에** 그림을 만든다. 그런데 그림 파일은 슬라이드 번호로
이름이 붙는다(`005.png` = 5번 장). 앞에 장이 하나 끼어들면 번호가 전부 한 칸씩
밀리고, `005.png` 는 남의 장 그림이 된다. 예순 장짜리 원고에서 두 번째 장을 하나
늘리면 쉰여덟 장의 그림이 통째로 어긋난다.

그래서 프롬프트는 **번호가 아니라 이름표(`data_id`)에 매단다**(`core/ledger.py`).
번호는 내보낼 때만 매긴다. 그 결과:

- 몸통이 안 바뀐 장은 프롬프트를 **다시 안 만든다** — 이미 그린 그림과 안 어긋난다
- 새로 생기거나 바뀐 장만 `이미지프롬프트_부족분.json` 으로 나온다
- 번호가 밀린 장은 `이름바꾸기.txt` 에 `005.png → 007.png` 로 나온다

## 설치

```
setup.bat            (macOS/Linux 는 ./setup.sh)
```

- Python 3.10+ 와 `claude` CLI(Claude Code) 가 있어야 한다.
  **API 키가 아니라 구독 OAuth** 를 쓴다 — 터미널에서 `claude` 를 한 번 실행해
  로그인해 두면 된다. 부모 환경에 `ANTHROPIC_API_KEY` 가 있어도 자식에서 비워
  가로채지 못하게 한다(`llm/claude_provider.py::scrubbed_env`).
- `npm` 이 있으면 playwright 도 깐다. **b7(실측)에만 쓴다** — 없으면 그 단계만
  건너뛰고 원고는 그대로 나온다(다만 규약을 어겼는지 모르는 채로 나간다).

## 실행

```
run.bat              →  http://localhost:5187
```

포트가 5187 인 이유: 5178 은 발표 쇼케이스가 쓰고 5179 도 이미 물려 있다.
5178 의 뒤 두 자리를 바꾼 수라 두 앱을 나란히 적어도 눈에 띈다.

산출물은 앱 폴더 **밖**에 쌓인다(`git clean` 이 지울 수 없게):

```
D:\00work\book2json-out-260814\01_<원고>\
  01_원문/     pages.json · 본문.md
  02_목차/     outline.json · outline.overrides.json
  03_원고/     draft.json
  04_그림/     figures.json
  09_이미지/   원장.json          ← 이름표로 쌓이는 프롬프트 원장
  10_내보내기/ <장>_원고.html · 이미지프롬프트.json
               이미지프롬프트_부족분.json · 이름바꾸기.txt · 실측.json
  _cache/      단계 캐시 (input_hash · cost · status)
```

`BOOK2JSON_WORKSPACE` 로 자리를 옮길 수 있다.

## 여덟 단계

| | 단계 | 무엇 | Claude |
|---|---|---|---|
| 1 | `b1-pdf` | 쪽별 본문. 머리글·쪽번호·여백 상자를 걷어낸다 | ✗ |
| 2 | `b2-outline` | `h2` 묶음 + `h3` 장. **여기서 장 수가 정해진다** | opus |
| 3 | `b3-write` | 장별 몸통. 여덟 장씩 묶어 부른다 | opus |
|   | `b4-figure` | 장마다 인라인 SVG. 여섯 장씩 | opus |
| 4 | `b5-imgprompt` | 가로형 영어 프롬프트. **원장에 없는 장만** | sonnet |
| 5 | `b6-assemble` | 원고 한 파일로 조립 | ✗ |
|   | `b7-check` | 진짜 브라우저에 띄워 장마다 높이를 잰다 | ✗ |
| 6 | `b8-export` | JSON · 부족분 · 이름바꾸기 | ✗ |

**Claude 단계는 낡아도 자동으로 안 돈다.** 돈은 명시적 클릭에만 쓴다.
프롬프트 파일(`llm/prompts/*.md`)이 캐시 해시에 들어가 있어서, 프롬프트만 고쳐도
그 단계가 낡은 것으로 잡힌다.

실측 참고(새뮤얼슨 19장, 32쪽 · 4.4만 자 → 27장):
`b2` 약 4분 $1.08 · `b3` 약 3분 $2.26 · `b4` 약 11분 $1.97 · `b5` 약 2분 $0.34.

## 가로형에 대해 알고 갈 것 — 진짜 16:9 는 없다

`codex-prompt-img-studio` 의 `_ASPECT_SIZE` 는 `landscape`·`horizontal`·`16:9` 를
전부 같은 값 `1536x1024` 로 떨어뜨리고, gpt-image 의 네이티브 크기는
`1024x1024 / 1536x1024 / 1024x1536` 셋뿐이다. **가장 넓은 것이 3:2** 다.

받은 샘플(`_contex/…이미지프롬프트 (1).json`)이 `square` 인 이유는 그쪽 앱의 사진
자리가 세로 패널이어서 "landscape 로 두면 좌우 30~40% 가 잘린다" 는 판단이었다
(`260804-ppt2eduvideo/core/deck_builder.py:1679`). 우리는 반대로 1920×1080 프레임에
깔므로 그 제약이 없다.

★ 그래서 `aspect` 만 바꾸지 않았다. 샘플은 `"square 1:1 composition … center-cropped"`
가 **34개 프롬프트 본문에 전부 박혀** 있어서, `aspect` 만 `landscape` 로 돌리면
가로 캔버스 한가운데 정사각형 그림이 앉고 좌우가 빈다. 구도 문구까지 다시 썼다
(`pipeline/b5_imgprompt.py::style_hint`).

## 발표 쇼케이스에 넣는 법

1. `#/export` 에서 `<장>_원고.html` 을 내려받거나 경로를 복사한다
2. 쇼케이스(`localhost:5178`) → **새 발표** → **참고 자료** 칸에 끌어다 놓는다
3. `kind === "html"` 로 잡혀 `s2c-capture` 가 돌고, **`h3` 수 + 1(표지)** 만큼 장이 생긴다

직접 확인하려면:

```
node <쇼케이스>/tools/split_sections.mjs <원고.html> --out /tmp/x2.html
```

## 남은 것 — 발표 쇼케이스 쪽에서 할 일

`split_sections.mjs` 는 지금 `h3` 의 `data-id`/`data-say`/`data-img` 를 `<section>`
으로 옮기지 않는다(그 레포 전체에 `data-say`·`data-id` 참조가 하나도 없다).
저쪽을 업데이트할 때:

- `split_sections.mjs` 가 세 속성을 `<section>` 과 `#manifest` 로 옮기게 한다
- `htmldoc.py` 가 `manifest` 에서 `say` 를 읽어 등장 시각 추정에 쓴다
- `s3b_images.py` 는 지금 `build_prompt()` 로 프롬프트를 **조립**하는데, 원고에
  `data-img` 가 있으면 **그것을 그대로 쓰게** 바꾸고 출력 스키마를
  `codex-studio-slides@1` 에서 스튜디오가 읽는 아홉 칸 모양으로 맞춘다

이 앱이 그 셋을 미리 만족하는 원고를 내므로, 저쪽은 **읽는 쪽만** 고치면 된다.
원고 끝의 `<script type="application/json" id="imgprompts">` 블록에 이름표별
프롬프트가 통째로 들어 있어서, 속성을 파싱하지 않고 그것만 꺼내 써도 된다.

## 앞선 레포에서 가져온 것

UI·인증·잡 구조는 `260812-summary-shocase` 를 그대로 가져왔다. 바꾼 것은
브랜드 색(테라코타 `#9a4d33` → 딥 틸 `#2f6b66`) 여섯 줄뿐이다.

- `static/css/app.css` — 가져온 것. `static/css/pages.css` — 이 앱에서 더한 화면
- `llm/claude_provider.py`, `llm/errors.py` — 구독 OAuth 유지의 전부
- `core/{config,workspace,jobs,activity,steps}.py`, `pipeline/registry.py`
- 색을 다시 뽑으려면: `python render/theme.py "#2f6b66"` ·
  레일 위는 `python render/theme.py "#2f6b66" --on "#201e1b"`
