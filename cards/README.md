# cards — 토망치랩 뉴스 카드 조립기

3D 일러스트를 상단에 넣는 카드 방식 (SKILL v3.5 «일러스트 우선»).
레이아웃 수치는 워크샵 정본 `00_브랜드에셋/inner.py` §6.1 카드와 같은 값이다 —
캐러셀에서 나란히 놓였을 때 문법이 갈리면 안 된다.

```
상단 57.5%   일러스트 (덮기)
하단 42.5%   번호 → 헤드라인 → 본문(키워드 강조) → 출처 → 로고 워터마크
```

## 카드 2종

| 함수 | 용도 |
|---|---|
| `news_card()` | **본문형 — 기본.** 일러스트 + 헤드라인 + 본문 |
| `news_card_chart()` | 차트형. 미니 가로 막대 — 수치 소재용 |

## 파이프라인

**1. 캐릭터 배정 → 프롬프트** — 소식 주체로 캐릭터가 자동으로 정해진다 (SKILL §2 캐릭터 선택 규칙).

```python
import card

prompt = card.illust_prompt(
    "Anthropic",                                   # 소식 주체
    "pressing a wooden approval stamp onto papers" # 뉴스를 은유하는 소품/동작
)
# → <<<b3f8b6ec-...>>> Claudie, a plush mascot ... — pressing ...
#   Soft matte 3D render, Pixar-like clay toy aesthetic. ...
#   Absolutely no text, no letters, no numbers, no labels.
```

주체 매칭은 **좁은 것이 이긴다** — `"OpenAI Codex"` 는 지피가 아니라 **코디**.
로스터에 없는 주체(구글·메타 등)는 `None` → 캐릭터 없이 소품만으로 생성된다.

**2. 일러스트 생성** — Higgsfield `nano_banana_pro`, 1:1, 1k.
받은 이미지에 **글자가 보이면 재생성**한다 (§6.8 텍스트 검수 의무).

**3. 카드 렌더**

```python
card.news_card(
    no="01",
    headline="물어보던 AI, 오늘부터 그냥 합니다",
    body=["앤트로픽이 클로드 코드 기본값을 **오토 모드**로 전환했습니다.",
          "8월 14일부터 **Pro·Max·Team** 새 세션에 적용됩니다."],
    illust="shots/_illust.png",
    credit="claude.com/blog",
    out="out/02_announce.png",
)
```

본문의 `**키워드**` 는 시안 볼드로 렌더된다.

수치 카드:

```python
card.news_card_chart(
    no="02",
    headline="사람 13.6% vs 오토 모드 89%",
    rows=[("사람 검수", 13.6, "13.6%", False),
          ("오토 모드", 89.0, "89%", True)],   # 강조는 하나만
    body=["같은 위험 명령 **1,053개**를 흘려보낸 결과입니다."],
    illust="shots/_illust.png",
    credit="claude.com/blog",
    out="out/03_stats.png",
)
```

## 규칙

- **일러스트에 글자를 넣지 않는다.** 생성 모델은 한글을 못 쓰고 없는 숫자를 지어낸다.
  카드에 보이는 텍스트·수치는 **전부 이 모듈이 렌더**한다.
- **원문에 있는 수치만 넣는다.** 두 값을 나눠 "N배"를 새로 만드는 것도 원문에 그
  배수가 없으면 창작이다 (SKILL §6.5).
- **출처 줄은 필수.** 캡처가 빠진 자리를 출처 표기와 이중 소스 검증이 대신 진다.
- 논란·반박·정정 소재는 **여전히 캡처가 이긴다** — 그때는 일러스트 대신 원문을 쓰거나,
  일러스트 카드 하단에 원문 문장 조각을 병기한다.

## 의존

`Pillow` · 폰트 `NotoSansKR-VF.ttf`(없으면 맑은 고딕 폴백) · `assets/logo_unit_ink.png`.
