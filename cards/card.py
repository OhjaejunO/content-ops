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
CHARACTERS = {
    "claudie": {
        "name": "클로디",
        "element": "b3f8b6ec-d250-4d34-ac40-931a9b85eed1",
        "owns": "Claude / Anthropic",
        "look": ("Claudie, a plush mascot whose body is a terracotta sunburst, "
                 "soft fluffy fur, two small arms and two legs between the sun rays, "
                 "big glossy eyes and a warm smile"),
    },
    "kyu": {
        "name": "큐",
        "element": "15aa79c0-6798-4ba3-b380-f0fbb2d700a6",
        "owns": "Qwen / 알리바바",
        "look": ("Kyu, a felt hexagonal star plush in white and indigo interlocking "
                 "panels with a triangular belly patch"),
    },
    "gpty": {
        "name": "지피",
        "element": "2c507dad-2e4c-4a02-856a-cc37483407b7",
        "owns": "OpenAI / ChatGPT",
        "look": ("Gpty, a felt wreath of six interlocking rings in white and charcoal, "
                 "no nose"),
    },
    "codie": {
        "name": "코디",
        "element": "39e0489a-4b6d-4332-9429-1676270e2823",
        "owns": "Codex",
        "look": ("Codie, a sky-blue flower-blob plush with a navy window face showing "
                 "a `>_` prompt"),
    },
}

#: 주체 문자열 → 캐릭터 키. 소문자로 매칭한다.
_SUBJECT_MAP = [
    (("anthropic", "claude", "클로드", "앤트로픽"), "claudie"),
    (("codex", "코덱스"), "codie"),
    (("openai", "chatgpt", "gpt", "오픈ai", "챗gpt"), "gpty"),
    (("qwen", "alibaba", "큐원", "알리바바"), "kyu"),
]


def pick_character(subject):
    """소식 주체 문자열에서 담당 캐릭터 키를 고른다.

    Codex 는 OpenAI 산하지만 **코디가 따로 있다** — 더 좁은 매칭이 이긴다.
    그래서 _SUBJECT_MAP 에서 codex 를 openai 보다 먼저 본다.
    아는 주체가 없으면 None — 그 소식은 캐릭터 없이 소품만으로 간다(SKILL §2).
    """
    s = (subject or "").lower()
    for keys, ch in _SUBJECT_MAP:
        if any(k in s for k in keys):
            return ch
    return None


ILLUST_STYLE = (
    "Soft matte 3D render, Pixar-like clay toy aesthetic. "
    "Clean light gray studio backdrop, soft gradient, gentle floor shadows, "
    "bright even lighting, teal and white accents. "
    "Square 1:1, generous empty space. "
    "Absolutely no text, no letters, no numbers, no labels."
)


def illust_prompt(subject, motif):
    """일러스트 생성 프롬프트를 만든다.

    subject = 소식 주체("Anthropic" 등) → 캐릭터 자동 배정
    motif   = 뉴스 내용을 은유하는 소품/동작 (영문 1~2문장)

    no-text 조항은 고정부라 호출부가 빼먹을 수 없다 — 카드의 글자는 전부
    card.py 가 렌더한다는 것이 이 파이프라인의 전제다.
    """
    ch = pick_character(subject)
    if ch:
        c = CHARACTERS[ch]
        head = f"<<<{c['element']}>>> {c['look']} — {motif}"
    else:
        head = motif
    return f"{head} {ILLUST_STYLE}"


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


def _paste_illust(canvas, path, top_h):
    """상단 비주얼 — 덮기(cover). 1:1 일러스트는 위아래가 잘리므로
    프롬프트의 `generous empty space` 가 그 여유를 만든다."""
    im = Image.open(path).convert("RGB")
    sc = max(W / im.width, top_h / im.height)
    nw, nh = round(im.width * sc), round(im.height * sc)
    im = im.resize((nw, nh), Image.LANCZOS)
    # 세로 중앙 — 캡처와 달리 일러스트는 주인공이 가운데 있다.
    canvas.paste(im, ((W - nw) // 2, (top_h - nh) // 2))


def _footer(canvas, credit):
    """출처 + 로고 워터마크(하단 중앙). 출처는 로고 바로 위 고정 —
    본문 줄 수가 달라져도 자리가 흔들리지 않는다."""
    lg = _load_logo()
    d = ImageDraw.Draw(canvas)
    if credit:
        d.text((PAD_X, H - lg.height - CREDIT_GAP), credit, font=font(25, 700), fill=GRAY)
    canvas.paste(lg, ((W - lg.width) // 2, H - lg.height - LOGO_BOTTOM), lg)


def _head_block(canvas, no, headline, y):
    """번호 → 헤드라인. §6.1 순서 고정."""
    d = ImageDraw.Draw(canvas)
    if no:
        d.text((PAD_X, y), str(no), font=font(44, 900), fill=CYAN_D)
        y += 64
    lines = _wrap(d, headline, 54, 900, W - PAD_X * 2)
    fh = _fit(d, lines, 54, 900, W - PAD_X * 2)
    for ln in lines:
        d.text((PAD_X, y), ln, font=fh, fill=INK)
        y += round(fh.size * 1.32)
    return y


# ── 카드 2종 ────────────────────────────────────────────────────────
def news_card(no, headline, body, illust, credit, out, top=TOP):
    """본문형 (기본) — 일러스트 + 헤드라인 + 본문(키워드 강조).

    body 는 줄 리스트. `**키워드**` 로 감싼 부분이 시안 볼드로 렌더된다.
    """
    canvas = _base()
    top_h = round(H * top)
    _paste_illust(canvas, illust, top_h)

    y = _head_block(canvas, no, headline, top_h + 40) + 16
    d = ImageDraw.Draw(canvas)
    plain = [_strip_emph(l) for l in body]
    fb = _fit(d, plain, 30, 500, W - PAD_X * 2)
    for ln in body:
        _draw_emph(d, PAD_X, y, ln, fb.size, W - PAD_X * 2)
        y += round(fb.size * 1.52)

    _footer(canvas, credit)
    canvas.convert("RGB").save(out, quality=95)
    return out


def news_card_chart(no, headline, rows, body, illust, credit, out, top=0.42):
    """차트형 — 미니 가로 막대. 수치 소재용.

    rows = [(라벨, 값, 표시문자열, 강조여부), ...]
    **원문에 있는 수치만 넣는다** — 두 값을 나눠 'N배'를 새로 만드는 것도
    원문에 그 배수가 없으면 창작이다 (SKILL §6.5).
    강조는 하나만 — 시안이 여럿이면 '여기를 보라'는 신호가 죽는다.

    상단 비주얼은 막대에 자리를 내주기 위해 기본 42%로 줄인다.
    """
    canvas = _base()
    top_h = round(H * top)
    _paste_illust(canvas, illust, top_h)

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

    _footer(canvas, credit)
    canvas.convert("RGB").save(out, quality=95)
    return out
