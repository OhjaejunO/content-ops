# -*- coding: utf-8 -*-
"""토망치랩 뉴스 카드 — 3D 일러스트 상단형 (SKILL v3.4 규격)

원문 캡처 대신 **3D 일러스트를 상단에 넣는 새 카드 방식**이다.
레이아웃 수치는 워크샵 정본 `00_브랜드에셋/inner.py` 의 §6.1 카드와 **같은 값**을
쓴다 — 캐러셀에서 나란히 놓였을 때 문법이 갈리면 안 되기 때문이다.

    상단 57.5%  일러스트 (덮기)
    하단 42.5%  번호 → 헤드라인 → 본문(키워드 강조) → 출처 → 로고 워터마크

카드 2종
    news_card(...)        본문형 — **기본**. 일러스트 + 헤드라인 + 본문
    news_card_chart(...)  차트형 — 미니 가로 막대. 수치 소재용으로 남겨둠

**일러스트에는 글자를 넣지 않는다.** AI 생성 모델은 한글을 못 쓰고, 영문·숫자도
없는 값을 지어낸다. 카드에 보이는 모든 텍스트·수치는 이 모듈이 렌더한다.
프롬프트는 `illust_prompt()` 가 만들며 no-text 조항이 고정부에 박혀 있다.

사용:
    import card
    card.news_card(
        no="01",
        headline="물어보던 AI, 오늘부터 그냥 합니다",
        body=["앤트로픽이 클로드 코드 기본값을 **오토 모드**로 전환.",
              "8월 14일부터 **Pro·Max·Team** 새 세션에 적용됩니다."],
        illust="shots/_illust.png",
        credit="claude.com/blog",
        out="02_announce.png",
    )

본문의 `**키워드**` 는 시안으로 강조 렌더된다.
"""
import os
import re

from PIL import Image, ImageDraw, ImageFont

import freshness

# ── 신선도 검사 (2026-08-15 신설) ────────────────────────────────────
# **임포트되는 순간 이 클론이 origin/main 을 따라잡았는지 본다.**
#
# 빌드 스크립트마다 한 줄씩 넣는 방식은 넣는 것을 잊은 스크립트가 곧 구멍이 되고,
# 구멍이 있는지 아무도 모른다. `content-ops/cards` 를 쓰는 빌드는 전부 이 모듈을
# 임포트하므로 여기 한 곳이면 새 스크립트도 자동으로 덮인다.
#
# 근거: 2026-08-15 지피 씬 6장이 회색 스튜디오 배경으로 나왔다. 프롬프트가 아니라
# **판본이 낡았던 것**이고(PR #9 미반영), 그 사실을 알리는 신호가 아무 데도 없었다.
# 크레딧을 쓰고 나서야 실물로 알았다 — 정관 §0 «조용히 실패하는 코드»다.
#
# 끄는 법과 이유는 `freshness` 모듈 상단에 적어 뒀다. 끄면 배너가 찍힌다.
freshness.assert_fresh()

# ── 규격 (정본: workshop/00_브랜드에셋/brand.py · inner.py) ──────────
# 값을 여기서 바꾸면 워크샵 카드와 문법이 갈린다. 고칠 일이 생기면 정본을
# 먼저 고치고 이 파일을 맞춘다.
W, H = 1080, 1350
TOP = 0.575                      # 상단 비주얼 비율 (§6.1 은 55~60% 허용)

WHITE = (255, 255, 255)
BG = WHITE
CYAN = (52, 220, 230)            # 면(뱃지·막대)에 쓴다
CYAN_D = (23, 138, 150)          # 순백 위 텍스트용 진한 시안
INK = (28, 32, 40)
GRAY = (120, 126, 136)
BODY = (70, 78, 88)              # 본문 회색 — inner._v3_bottom 과 같은 값

PAD_X = 64                       # 좌우 여백
LOGO_W = 330
LOGO_BOTTOM = 62                 # 로고 아래 여백
CREDIT_GAP = 104                 # 로고 위 출처 줄 위치

DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(DIR, "assets")
LOGO_INK = os.path.join(ASSETS, "logo_unit_ink.png")

_VF = r"C:\Windows\Fonts\NotoSansKR-VF.ttf"
_MG_BD = r"C:\Windows\Fonts\malgunbd.ttf"
_MG_RG = r"C:\Windows\Fonts\malgun.ttf"


# ── 캐릭터 배정 (SKILL §2 로스터) ────────────────────────────────────
# 소식의 **주체**가 누구냐로 고른다. 도구가 아니라 발표한 회사·제품이 기준이다.
# element 는 전체 UUID 를 `<<<...>>>` 로 넘긴다 — 축약 8자리는 동작하지 않는다.
#: 폐기 element — 절대 재사용 금지. 남아 있어도 구버전 조형이 나온다 (SKILL §2 폐기 표와 동기).
RETIRED_ELEMENTS = {
    "b3f8b6ec-d250-4d34-ac40-931a9b85eed1": "claudie_final (클로디 v1 · 테라코타 햇살 · 2026-08-19 v2 로 교체)",
    "6d4b9466-14c0-49af-89b0-02d1b9b15b3d": "claudie (클로디 v1 이전)",
    "ef2e1dba-e5a9-4270-b6a4-7cb4744b4d2f": "kyu (큐 구버전)",
    "23b65bbc-835e-449d-b595-7cee1d44be59": "codie (코디 구버전)",
}

CHARACTERS = {
    # 클로디 v2 (2026-08-19 교체 · JJ 결정 2026-08-18). v1 은 아래 RETIRED_ELEMENTS.
    # 신규 편(ep17 이후)부터. 기존 발행분·로고·광고 릴스는 v1 유지 — 소급 교체 없음.
    # 정본 기록: workshop/assets/characters/claudie_v2/등록준비.md
    "claudie": {
        "name": "클로디",
        "element": "ca26eff9-4887-410f-8f96-581541d144f2",
        "owns": "Claude / Anthropic",
        "look": ("Claudie, a toy mascot with a wide rounded-square body in coral (#F07050), "
                 "smooth matte plastic toy texture, two vertical black rounded-slot eyes "
                 "set wide apart, no mouth, no nose, two short stubby arms on the sides "
                 "and four short stubby legs in a row underneath, standing upright"),
        # 씬 라이브러리 폴더. v1 씬(claudie/)과 섞이지 않게 따로 둔다 — 재질·형태가 다른 캐릭터다.
        "folder": "claudie_v2",
    },
    "kyu": {
        "name": "큐",
        "element": "15aa79c0-6798-4ba3-b380-f0fbb2d700a6",
        # 2026-08-19 JJ 정정: 큐는 **Qwen(모델) 명시 소재 전용**이다. 알리바바의 다른 제품·회사 소식
        # (HappyShrimp 음악 모델 등)은 로스터 밖 → 캐릭터 없이 소품·상황 일러스트(props). 회사≠모델.
        "owns": "Qwen (모델 명시 소재만 — 알리바바 회사 소식은 무캐릭터)",
        "look": ("Kyu, a felt hexagonal star plush in white and indigo interlocking "
                 "panels with a triangular belly patch"),
    },
    "gpty": {
        "name": "지피",
        "element": "2c507dad-2e4c-4a02-856a-cc37483407b7",
        "owns": "OpenAI / ChatGPT",
        # 재질을 두 번 말한다. `a felt wreath` 만으로는 «Pixar-like clay toy»
        # 고정부에 끌려 플라스티신처럼 매끈하게 나온다 — 1차 생성에서 같은 개념
        # 두 장 중 한 장이 실제로 그렇게 나왔고, 그 장을 기준샷으로 삼았으면
        # 이후 씬이 전부 점토로 끌려갔을 것이다(gpty/index.md 2026-08-15).
        # 종전에는 이 문구를 **호출부가 손으로 붙여 왔다.** 프롬프트를 손으로
        # 조립하지 말라는 SKILL §6 과 어긋나고, 빠뜨리면 조용히 재질이 갈린다.
        "look": ("Gpty, a felt wreath of six interlocking rings in white and charcoal, "
                 "no nose, the body stitched felt with visible fuzzy nap and seams, "
                 "never smooth clay"),
    },
    "codie": {
        "name": "코디",
        "element": "39e0489a-4b6d-4332-9429-1676270e2823",
        "owns": "Codex",
        "look": ("Codie, a sky-blue flower-blob plush with a navy window face showing "
                 "a `>_` prompt"),
    },
    "manu": {
        "name": "마누",
        "element": "db952663-f6f6-41f2-8c39-493a842edf26",
        "owns": "Manus",
        "look": ("Manu, a plush mascot whose whole body is a soft rounded hand, "
                 "cream-white plush with bold charcoal outline piping tracing every "
                 "edge and finger, three short charcoal accent strokes floating above, "
                 "big glossy eyes and a small stitched smile on the back of the hand"),
    },
    "groki": {
        "name": "그로키",
        "element": "2103c070-a6f9-486f-a65c-093c3e34702b",
        "owns": "Grok / xAI / SpaceXAI (Grok Bot 포함)",
        "look": ("Grokie, a rounded cream-white plush mascot with short stubby arms "
                 "and legs, big glossy eyes and a calm smile, one large black emblem "
                 "embroidered flat on its belly — a bold ring cut through by a "
                 "diagonal blade tapering to sharp points beyond the ring"),
    },
}

#: 주체 문자열 → 캐릭터 키. 소문자로 매칭한다.
#: **순서가 곧 우선순위다** — 먼저 걸리는 항목이 이긴다(§2 "좁은 것이 이긴다").
#: 그록·마누스는 기존 항목과 문자열이 겹치지 않아 뒤에 붙여도 판정이 바뀌지 않는다.
#: 그록 봇은 그록의 제품이므로 **따로 두지 않고 그로키가 맡는다** — 봇 로고를
#: 우리 캐릭터로 다시 만들면 모작이 되기 때문이다(SKILL §2).
_SUBJECT_MAP = [
    (("anthropic", "claude", "클로드", "앤트로픽"), "claudie"),
    (("codex", "코덱스"), "codie"),
    (("openai", "chatgpt", "gpt", "오픈ai", "챗gpt"), "gpty"),
    # 회사≠모델 (2026-08-19 JJ 정정): «alibaba/알리바바» 는 매핑하지 않는다 — 큐는 Qwen 소재만.
    # ep20 에서 HappyShrimp(알리바바 음악 모델)가 «Alibaba» 주체로 큐에 걸렸던 것이 계기다.
    (("qwen", "큐원"), "kyu"),
    (("manus", "마누스"), "manu"),
    (("grok", "그록", "xai", "spacexai", "엑스ai"), "groki"),
]


def pick_character(subject):
    """소식 주체 문자열에서 담당 캐릭터 키를 고른다.

    Codex 는 OpenAI 산하지만 **코디가 따로 있다** — 더 좁은 매칭이 이긴다.
    그래서 _SUBJECT_MAP 에서 codex 를 openai 보다 먼저 본다.
    아는 주체가 없으면 None — 그 소식은 캐릭터 없이 소품만으로 간다(SKILL §2).
    **회사와 모델은 다르다** — 큐는 Qwen 소재에만 걸리고 «Alibaba» 만으로는 걸리지 않는다
    (2026-08-19). 같은 원리로 다른 캐릭터도 담당 «제품/모델» 이름이 주체에 있어야 한다.
    """
    s = (subject or "").lower()
    for keys, ch in _SUBJECT_MAP:
        if any(k in s for k in keys):
            return ch
    return None


#: 씬이 놓이는 공간. **스튜디오가 아니라 실제 장소**를 그린다.
#: 씬마다 다르게 할 필요는 없다 — 상황에 맞으면 같은 편 안에서 반복돼도 좋고,
#: 오히려 같은 사무실이 이어지면 이야기가 이어진다. 상황이 사무실이 아닐 때만
#: `illust_prompt(..., place=...)` 로 바꾼다 (서버룸·회의실·집 작업실 등).
DEFAULT_PLACE = ("a quiet modern office corner with a desk, low shelves and a plant, "
                 "daylight coming from a window to one side")

#: 스타일 고정부. `{place}` 만 호출부가 바꾼다.
#:
#: 종전 고정부는 "Clean light gray studio backdrop … teal and white accents" 였다.
#: 두 가지가 문제였다 — ① 모든 씬이 같은 회색 스튜디오에 떠 있어 상황이 안 읽혔고,
#: ② `teal accents` 지시가 배경에 **정체불명 청록 도형**으로 나타났다(그로키 씬들
#: 좌상단·우하단에 실제로 떴다). 브랜드 색은 소품에만 들어가야 한다.
_STYLE_HEAD = (
    "Soft matte 3D render, Pixar-like clay toy aesthetic. "
    "Set in a real place, not a studio: {place}. "
    "Shallow depth of field — the room falls softly out of focus behind the subject, "
    "which stays crisp and clearly separated from it. Warm natural daylight. "
    "Teal appears only on physical props in the scene such as a chair, a laptop or a cable, "
    "never as floating shapes, gradients or graphic panels in the background. "
)

#: 화면비별 구도 지시. 본문 카드는 1:1(상단 밴드에 덮기), 표지는 4:5 상단 2/3 구도다
#: (SKILL §6). 이 문구를 손으로 고쳐 쓰지 말 것 — 프롬프트를 새로 쓰면 톤이 갈린다.
_FRAMING = {
    "1:1": "Square 1:1, the subject large in frame with calm space around it. ",
    # 표지는 **글자가 그림 위에 얹히는 유일한 카드**다. `template._scheme` 이 이 구역
    # 밝기로 잉크/흰 글씨를 고르는데, 배경이 실제 공간이 되면서 그 밝기가 임계선
    # (brand.LUMA_THRESHOLD=140) 근처로 내려왔다 — 실측 109·125·138 로 색이 흔들렸다.
    # "calm / low-contrast" 는 **어두워도 만족된다.** 그래서 밝기를 명시한다.
    "4:5": ("Vertical 4:5 composition, subject held in the upper two thirds; "
            "the lower third is a plain, brightly lit, unobstructed floor — "
            "no furniture, no cables and no strong shadows crossing it. "),
}

_NO_TEXT = "Absolutely no text, no letters, no numbers, no labels."

#: 기존 호출부 호환 — 1:1 고정부 전문(기본 공간 적용).
ILLUST_STYLE = _STYLE_HEAD.format(place=DEFAULT_PLACE) + _FRAMING["1:1"] + _NO_TEXT


def illust_prompt(subject, motif, ratio="1:1", place=None):
    """일러스트 생성 프롬프트를 만든다.

    subject = 소식 주체("Anthropic" 등) → 캐릭터 자동 배정
    motif   = 뉴스 내용을 은유하는 소품/동작 (영문 1~2문장)
    ratio   = "1:1"(본문 카드 기본) 또는 "4:5"(표지 — 상단 2/3 구도)
    place   = 씬이 놓이는 실제 공간. 생략하면 `DEFAULT_PLACE`(사무실 한켠).
              **씬마다 바꿀 필요는 없다** — 상황이 사무실이 아닐 때만 바꾼다.

    no-text 조항은 고정부라 호출부가 빼먹을 수 없다 — 카드의 글자는 전부
    card.py 가 렌더한다는 것이 이 파이프라인의 전제다.
    """
    if ratio not in _FRAMING:
        raise ValueError(f"모르는 화면비다: {ratio!r} (쓸 수 있는 값: {sorted(_FRAMING)})")
    ch = pick_character(subject)
    if ch:
        c = CHARACTERS[ch]
        head = f"<<<{c['element']}>>> {c['look']} — {motif}"
    else:
        head = motif
    style = _STYLE_HEAD.format(place=place or DEFAULT_PLACE)
    return f"{head} {style}{_FRAMING[ratio]}{_NO_TEXT}"


# ── 렌더 헬퍼 ────────────────────────────────────────────────────────
_logo = None


def _load_logo():
    global _logo
    if _logo is None:
        im = Image.open(LOGO_INK).convert("RGBA")
        _logo = im.resize((LOGO_W, max(1, round(im.height * LOGO_W / im.width))),
                          Image.LANCZOS)
    return _logo


def font(size, weight=700):
    if os.path.exists(_VF):
        f = ImageFont.truetype(_VF, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        return f
    return ImageFont.truetype(_MG_BD if weight >= 600 else _MG_RG, size)


def _fit(d, lines, size, weight, maxw):
    lines = [l for l in lines if l]
    if not lines:
        return font(size, weight)
    while size > 20:
        f = font(size, weight)
        if max(d.textlength(l, font=f) for l in lines) <= maxw:
            return f
        size -= 2
    return font(20, weight)


def _wrap(d, text, size, weight, maxw):
    """공백 기준 래핑 — inner._wrap 과 같은 취지."""
    f = font(size, weight)
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


_EMPH = re.compile(r"\*\*(.+?)\*\*")


def _strip_emph(s):
    return _EMPH.sub(r"\1", s)


def _draw_emph(d, x, y, line, size, maxw):
    """`**키워드**` 를 시안 볼드로 렌더. 나머지는 본문 회색.

    한 줄을 조각으로 잘라 이어 그린다 — 강조가 줄바꿈을 건너뛰지 않도록
    호출부에서 이미 줄이 확정된 상태로 들어온다.
    """
    fr = font(size, 500)
    fb = font(size, 800)
    cx = x
    pos = 0
    for m in _EMPH.finditer(line):
        pre = line[pos:m.start()]
        if pre:
            d.text((cx, y), pre, font=fr, fill=BODY)
            cx += d.textlength(pre, font=fr)
        key = m.group(1)
        d.text((cx, y), key, font=fb, fill=CYAN_D)
        cx += d.textlength(key, font=fb)
        pos = m.end()
    tail = line[pos:]
    if tail:
        d.text((cx, y), tail, font=fr, fill=BODY)


def _base():
    return Image.new("RGBA", (W, H), BG + (255,))


# ── 원문 조각 (ep14 에서 승격) ────────────────────────────────────────
# 일러스트가 기본이 된 뒤에도 **근거 문장은 실물로 보여야** 하는 카드가 있다
# (§6 "논란·반박·정정은 여전히 캡처가 이긴다", "근거가 의심받을 만한 수치").
# ep14 가 스크립트 안에 들고 있던 조각 크롭 로직을 여기로 옮긴다 — 편마다
# 복사되면 언젠가 갈린다(§4 색 상수와 같은 이유).

def line_bands(path, thresh=200, min_ink=0.002, min_gap=6):
    """글자 줄의 y 밴드 목록을 돌려준다. 잉크가 있는 행이 이어지는 구간이 한 줄이다."""
    im = Image.open(path).convert("L")
    w, h = im.size
    px = im.load()
    rows = []
    for y in range(h):
        c = sum(1 for x in range(0, w, 3) if px[x, y] < thresh)
        rows.append(c / (w / 3) > min_ink)
    out, start, gap = [], None, 0
    for y, on in enumerate(rows):
        if on:
            if start is None:
                start = y
            gap = 0
        else:
            if start is not None:
                gap += 1
                if gap >= min_gap:
                    out.append((start, y - gap))
                    start = None
    if start is not None:
        out.append((start, h - 1))
    return [b for b in out if b[1] - b[0] > 10], (w, h)


def crop_lines(path, ranges=None, pad=14):
    """줄 번호 구간들을 **줄 경계**에서 잘라 세로로 잇는다.

    y 좌표로 자르면 문장이 허리에서 끊긴다 — 잘린 문장은 근거 구실을 못 한다.
    ranges 를 비우면 그 캡처의 전 줄을 쓰되 위아래 여백만 줄 경계로 정리한다.
    구간이 둘 이상이면 사이에 생략 표시(⋯)를 넣는다 — 중간을 들어냈다는
    사실이 카드에서 보여야 한다.
    """
    bs, (w, h) = line_bands(path)
    if not bs:
        raise ValueError(f"글자 줄을 못 찾았다(빈 캡처?): {path}")
    if ranges is None:
        ranges = [(0, len(bs) - 1)]
    for first, last in ranges:
        assert last < len(bs), (
            f"{os.path.basename(path)}: {last}행을 요구했는데 {len(bs)}행뿐이다")
    src = Image.open(path).convert("RGB")
    pieces = [src.crop((0, max(0, bs[f][0] - pad), w, min(h, bs[l][1] + pad)))
              for f, l in ranges]
    return stack_pieces(pieces)


def stack_pieces(pieces, gap_h=62, bg=None, mark=(150, 158, 168)):
    """조각들을 세로로 잇고 사이마다 생략 표시(⋯)를 찍는다.

    bg 를 안 주면 첫 조각의 좌상단 픽셀을 배경으로 쓴다 — 원문이 순백이 아닌
    페이지(크림 배경 블로그 등)에서 이음매가 흰 띠로 튀는 것을 막는다.
    """
    if len(pieces) == 1:
        return pieces[0]
    w = max(pc.width for pc in pieces)
    if bg is None:
        bg = pieces[0].convert("RGB").getpixel((1, 1))
    total = sum(pc.height for pc in pieces) + gap_h * (len(pieces) - 1)
    out = Image.new("RGB", (w, total), bg)
    d = ImageDraw.Draw(out)
    y = 0
    for i, pc in enumerate(pieces):
        out.paste(pc, ((w - pc.width) // 2, y))
        y += pc.height
        if i < len(pieces) - 1:
            # 카드에서 이 조각은 크게 줄어든다. 작게 찍으면 먼지처럼 보여
            # 생략 표시 구실을 못 한다 — 실물 확인 후 키운 값(ep14).
            f = font(52, 800)
            tw = d.textlength("⋯", font=f)
            d.text(((w - tw) / 2, y + 2), "⋯", font=f, fill=mark)
            y += gap_h
    return out


def evidence(canvas, crop_im, y, w, label, label_fill=(168, 177, 188)):
    """원문 조각 + 테두리 + 출처 라벨. 넘치면 **소리내어 죽는다.**

    조용히 잘리면 발행팩 기재와 산출물이 어긋난 채로 남는다 (ep14 실제 사고).
    반환: 라벨까지 포함한 아래쪽 y.
    """
    sc = w / crop_im.width
    im = crop_im.resize((w, round(crop_im.height * sc)), Image.LANCZOS)
    bottom = y + im.height + 56
    assert bottom <= canvas.height, (
        f"근거 조각이 캔버스를 {bottom - canvas.height}px 넘친다 "
        f"(y={y}, 조각높이={im.height}, 캔버스={canvas.height}) — 도해를 줄여라")
    x = (canvas.width - w) // 2
    canvas.paste(im, (x, y))
    d = ImageDraw.Draw(canvas)
    d.rectangle([x - 1, y - 1, x + w, y + im.height], outline=(226, 231, 235), width=2)
    d.text((x, y + im.height + 12), label, font=font(26, 600), fill=label_fill)
    return bottom


def _paste_illust(canvas, path, top_h):
    """상단 비주얼 — 덮기(cover) 후 **밴드 크기로 잘라서** 붙인다.

    자르지 않고 그대로 붙이면 넘치는 부분이 하단 텍스트 영역을 침범한다.
    1:1 일러스트(1024²)를 1080 폭에 맞추면 세로가 1080이 되어 상단 밴드(776)를
    304px 넘기고, 그 회색 배경이 번호·헤드라인 뒤에 깔린다 — 2026-08-14 실제 사고.

    반환: 실제로 붙인 밴드 높이 (호출부 검증용).
    """
    im = Image.open(path).convert("RGB")
    sc = max(W / im.width, top_h / im.height)
    nw, nh = round(im.width * sc), round(im.height * sc)
    im = im.resize((nw, nh), Image.LANCZOS)

    # 세로 중앙 — 캡처와 달리 일러스트는 주인공이 가운데 있다.
    ox, oy = (nw - W) // 2, (nh - top_h) // 2
    band = im.crop((ox, oy, ox + W, oy + top_h))

    # 검증 ① 밴드 크기가 지정 비율과 정확히 같은가
    assert band.size == (W, top_h), f"일러스트 밴드 크기 불일치: {band.size} != {(W, top_h)}"
    # 검증 ② 이미지가 실제로 붙었는가 (단색·빈 이미지면 명암폭이 거의 없다)
    lo, hi = band.convert("L").getextrema()
    assert hi - lo > 12, f"일러스트가 비었거나 단색이다 (명암폭 {hi - lo}): {path}"

    canvas.paste(band, (0, 0))
    return top_h


def _paste_cutout(canvas, path, body_end_y):
    """텍스트 카드 우하단 캐릭터 누끼 (SKILL §6 3조건).

    ① 가독성을 침범하지 않는 위치(우하단) ② 카드 폭의 1/4 이하
    ③ **소스 캡처 카드에는 금지** — 캡처는 증거라 위에 아무것도 얹지 않는다.
    ③은 호출부가 지킨다. 이 함수는 ①②만 강제한다.
    """
    if not path or not os.path.exists(path):
        return
    cut = Image.open(path).convert("RGBA")
    cw = W // 4
    cut = cut.resize((cw, max(1, round(cut.height * cw / cut.width))), Image.LANCZOS)
    lg = _load_logo()
    # 본문 끝과 출처 줄 사이 빈 공간의 가운데. 로고·출처와 겹치지 않게 둔다.
    zone_top = body_end_y + 20
    zone_bottom = H - lg.height - CREDIT_GAP - 12
    cy = zone_top + max(0, (zone_bottom - zone_top - cut.height) / 2)
    canvas.alpha_composite(cut, (W - cw - 56, round(cy)))


def _room_check(y, credit, what="본문"):
    """본문 끝이 출처 줄·로고를 밀고 들어갔는지 검사한다.

    출처 줄과 로고는 본문 길이와 무관하게 **고정 위치**라(자리가 흔들리면 안 되므로),
    본문이 길어지면 조용히 겹쳐 찍힌다. 겹친 카드는 육안 검수에서야 발견되고
    그때는 이미 발행팩에 '3줄'이라고 적혀 있다 — ep14 근거 잘림과 같은 경로다.
    줄이는 것은 사람이 정한다(§5.8: 정보가 많으면 줄이지 말고 장수로 분산).
    """
    lg = _load_logo()
    limit = H - lg.height - (CREDIT_GAP if credit else LOGO_BOTTOM) - 12
    assert y <= limit, (
        f"{what}이 {round(y - limit)}px 넘쳐 "
        f"{'출처 줄' if credit else '로고'}를 덮는다 (끝 y={round(y)}, 한계={limit}) "
        f"— 줄을 줄이거나 카드를 나눠라")


def _footer(canvas, credit):
    """출처 + 로고 워터마크(하단 중앙). 출처는 로고 바로 위 고정 —
    본문 줄 수가 달라져도 자리가 흔들리지 않는다."""
    lg = _load_logo()
    d = ImageDraw.Draw(canvas)
    if credit:
        d.text((PAD_X, H - lg.height - CREDIT_GAP), credit, font=font(25, 700), fill=GRAY)
    canvas.paste(lg, ((W - lg.width) // 2, H - lg.height - LOGO_BOTTOM), lg)


def _head_block(canvas, no, headline, y, badge=None):
    """번호/배지 → 헤드라인. §6.1 순서 고정.

    badge 는 번호를 **대체한다** — 둘 다 그리지 않는다. 의견 카드가 소식 카드로
    읽히면 안 되므로 성격 표시(배지)가 순번(번호)보다 우선이다. ep11~13 의
    코멘트 카드가 배지를 달고 나갔고 그 문법을 유지한다.
    """
    d = ImageDraw.Draw(canvas)
    if badge:
        fb = font(30, 800)
        bw = d.textlength(badge, font=fb) + 56
        bh = 58
        d.rounded_rectangle([PAD_X, y, PAD_X + bw, y + bh],
                            radius=bh // 2, outline=CYAN_D, width=3)
        d.text((PAD_X + 28, y + (bh - fb.size * 1.34) / 2), badge, font=fb, fill=CYAN_D)
        y += bh + 20
    elif no:
        d.text((PAD_X, y), str(no), font=font(44, 900), fill=CYAN_D)
        y += 64
    lines = _wrap(d, headline, 54, 900, W - PAD_X * 2)
    fh = _fit(d, lines, 54, 900, W - PAD_X * 2)
    for ln in lines:
        d.text((PAD_X, y), ln, font=fh, fill=INK)
        y += round(fh.size * 1.32)
    return y


# ── 카드 2종 ────────────────────────────────────────────────────────
def news_card(no, headline, body, illust, credit, out, top=TOP, cutout=None,
              kicker=None, badge=None):
    """본문형 (기본) — 일러스트 + 헤드라인 + 본문(키워드 강조).

    body 는 줄 리스트. `**키워드**` 로 감싼 부분이 시안 볼드로 렌더된다.
    cutout = 담당 캐릭터 누끼(우하단 소형, §6 3조건). **소스 캡처 카드에는 주지 말 것.**
    kicker = 헤드라인과 본문 사이 소형 시안 라벨("토망치랩 요약" 등, ep11~13 관습).
    badge  = 번호 자리를 대신하는 테두리 알약("토망치 코멘트" 등). 번호보다 우선.
    """
    canvas = _base()
    top_h = round(H * top)
    band_h = _paste_illust(canvas, illust, top_h)
    assert band_h == round(H * top), f"상단 밴드 높이 불일치: {band_h} != {round(H * top)}"

    y = _head_block(canvas, no, headline, top_h + 40, badge=badge) + 16
    d = ImageDraw.Draw(canvas)
    if kicker:
        d.text((PAD_X, y), kicker, font=font(27, 800), fill=CYAN_D)
        y += 46
    plain = [_strip_emph(l) for l in body]
    fb = _fit(d, plain, 30, 500, W - PAD_X * 2)
    for ln in body:
        _draw_emph(d, PAD_X, y, ln, fb.size, W - PAD_X * 2)
        y += round(fb.size * 1.52)
    _room_check(y, credit)

    _paste_cutout(canvas, cutout, y)
    _footer(canvas, credit)
    canvas.convert("RGB").save(out, quality=95)
    return out


def news_card_chart(no, headline, rows, body, illust, credit, out, top=0.42, cutout=None):
    """차트형 — 미니 가로 막대. 수치 소재용.

    rows = [(라벨, 값, 표시문자열, 강조여부), ...]
    **원문에 있는 수치만 넣는다** — 두 값을 나눠 'N배'를 새로 만드는 것도
    원문에 그 배수가 없으면 창작이다 (SKILL §6.5).
    강조는 하나만 — 시안이 여럿이면 '여기를 보라'는 신호가 죽는다.

    상단 비주얼은 막대에 자리를 내주기 위해 기본 42%로 줄인다.
    """
    canvas = _base()
    top_h = round(H * top)
    band_h = _paste_illust(canvas, illust, top_h)
    assert band_h == round(H * top), f"상단 밴드 높이 불일치: {band_h} != {round(H * top)}"

    y = _head_block(canvas, no, headline, top_h + 40) + 28
    d = ImageDraw.Draw(canvas)

    vmax = max((r[1] for r in rows), default=1) or 1
    track_w = W - PAD_X * 2
    bar_h = 46
    fl = font(30, 700)
    fv = font(30, 900)
    for label, value, shown, hot in rows:
        d.text((PAD_X, y), label, font=fl, fill=INK)
        vw = d.textlength(shown, font=fv)
        d.text((W - PAD_X - vw, y), shown, font=fv, fill=CYAN_D if hot else GRAY)
        y += round(fl.size * 1.35)
        d.rounded_rectangle([PAD_X, y, PAD_X + track_w, y + bar_h],
                            radius=bar_h // 2, fill=(240, 243, 246))
        fill_w = max(bar_h, round(track_w * (value / vmax)))
        d.rounded_rectangle([PAD_X, y, PAD_X + fill_w, y + bar_h],
                            radius=bar_h // 2, fill=CYAN_D if hot else (198, 206, 214))
        y += bar_h + 30

    y += 6
    plain = [_strip_emph(l) for l in body]
    fb = _fit(d, plain, 29, 500, W - PAD_X * 2)
    for ln in body:
        _draw_emph(d, PAD_X, y, ln, fb.size, W - PAD_X * 2)
        y += round(fb.size * 1.52)
    _room_check(y, credit)

    _paste_cutout(canvas, cutout, y)
    _footer(canvas, credit)
    canvas.convert("RGB").save(out, quality=95)
    return out
