# -*- coding: utf-8 -*-
"""씬 라이브러리 — 재사용이 먼저, 생성은 없을 때만.

크레딧이 드는 것은 생성뿐이다. 그래서 이 모듈의 기본 동작은 **찾기**이고,
생성은 못 찾았을 때만 일어난다. 호출부가 순서를 뒤집을 수 없도록
`get_scene()` 하나로 묶어 두었다.

라이브러리 위치
    workshop/assets/characters/<캐릭터키>/
        claudie_block-lane.png      실제 씬
        index.md                    개념·키워드 표 (사람이 읽는 정본)
        scenes.json                 같은 내용의 기계 판독본 (find_scene 이 읽는다)

**생성의 경계 — 솔직히 적어 둔다.**
Higgsfield 는 이 저장소에 API 키가 없고, 생성은 MCP 툴로만 된다. 파이썬이
직접 호출하지 못한다. 그래서 `get_scene()` 은 씬이 없을 때 **생성 지시서**를
돌려준다 — 프롬프트와 저장될 경로가 확정된 dict 다. 에이전트가 그 프롬프트로
MCP 를 호출하고 결과를 `save_scene()` 에 넘기면 라이브러리 등록까지 닫힌다.

    order = scenes.get_scene("Anthropic", "차단")
    if order["found"]:
        illust = order["path"]                  # 생성 없음 — 크레딧 0
    else:
        # 에이전트가 order["prompt"] 로 Higgsfield MCP 호출 후
        illust = scenes.save_scene(order, downloaded_png)

찾기·판정·저장·색인 갱신은 전부 코드가 한다. 사람이 개입하는 지점은
네트워크 호출 한 번뿐이다.
"""
import json
import os
import re
import shutil

import card

# 라이브러리 루트 — 워크샵 자산. content-ops 밖이라 경로로 참조한다.
LIB = os.environ.get(
    "TOMANGCHI_SCENES",
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop\assets\characters",
)

#: 로스터에 없는 주체(구글·메타·마누스 등)의 씬이 모이는 폴더.
#: SKILL §2 는 그런 소식을 **캐릭터 없이 소품만으로** 가라고 한다. 캐릭터가 없다고
#: 라이브러리 밖에 두면 같은 소품을 매 화 다시 생성하게 되므로, 캐릭터 자리에
#: 이 버킷을 넣어 조회·저장 경로를 하나로 유지한다.
PROPS = "props"

#: 개념 → 검색 키워드. index.md 의 «키워드» 열과 같은 내용이다.
#: 새 개념을 만들면 여기와 index.md 둘 다에 적는다.
CONCEPTS = {
    "block": ["차단", "막다", "막기", "거부", "정지", "block", "deny", "위험"],
    "pass": ["통과", "허용", "자동", "진행", "pass", "allow", "흘려"],
    "scan": ["검사", "스캐너", "관문", "전수", "scan", "gate", "필터", "분류기"],
    "approve": ["승인", "도장", "허가", "결재", "approve", "stamp"],
    "deadline": ["마감", "달력", "카운트다운", "기한", "종료일", "deadline", "calendar"],
    "drop": ["유실", "누락", "떨어짐", "구멍", "사라짐", "소실", "drop", "loss"],
    # ── 설명 포즈 (2026-08-15 신설) ───────────────────────────────────
    # 증거 카드(캡처·차트·영상)에는 캐릭터를 얹지 않는다(SKILL §6.1) — 실물 위에
    # 연출을 올리면 증거가 아니게 되기 때문이다. 대신 증거 앞뒤에 캐릭터가 설명하는
    # 카드를 두고, 그 포즈들이 여기 모인다. 소재와 무관한 순수 포즈라 **편이 바뀌어도
    # 그대로 재사용된다** — 이 버킷이 재생성을 가장 많이 막아줄 자리다.
    #
    # ⚠️ 여기 없는 개념은 `_concept_key` 가 None 을 돌려주고, 그러면 `find_scene` 이
    # 영원히 못 찾는다. `get_scene` 은 슬러그로 **저장은 하므로** 파일은 쌓이는데
    # 조회가 안 되는 상태가 된다 — 라이브러리를 만든 이유가 사라진다.
    # 새 포즈를 쓰기 전에 반드시 이 표에 먼저 올릴 것.
    "explain": ["설명", "설명하기", "안내", "말하기", "explain", "presenting"],
    "point": ["가리키기", "가리킴", "지목", "시선", "point", "pointing"],
    "surprise": ["놀람", "놀라기", "충격", "의외", "surprise", "shocked"],
    "arms": ["팔짱", "단호", "경고", "arms-crossed", "firm"],
    "tilt": ["갸웃", "의문", "헷갈림", "tilt", "puzzled"],
    "cover": ["표지", "커버", "cover"],
}


def bucket(subject):
    """씬이 들어갈 폴더 키. 로스터 밖 주체는 전부 `props` 로 모인다."""
    return card.pick_character(subject) or PROPS


def _dir(character):
    return os.path.join(LIB, character)


def _index_path(character):
    return os.path.join(_dir(character), "scenes.json")


def _load_index(character):
    p = _index_path(character)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    # scenes.json 이 아직 없으면 폴더의 파일명에서 개념을 역추출한다.
    # (index.md 를 사람이 먼저 쓰고 json 을 안 만든 경우를 구제)
    out = {}
    d = _dir(character)
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".png"):
                continue
            m = re.match(rf"{character}_([a-z0-9\-]+?)(-alt)?\.png$", fn)
            if m:
                out.setdefault(m.group(1), []).append(fn)
    return out


def _save_index(character, idx):
    with open(_index_path(character), "w", encoding="utf-8", newline="\n") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


def _concept_key(concept):
    """한국어·영어 개념어를 라이브러리 키로 정규화한다."""
    c = (concept or "").strip().lower()
    if c in CONCEPTS:
        return c
    for key, words in CONCEPTS.items():
        if any(w in c for w in words):
            return key
    return None


def find_scene(subject, concept):
    """라이브러리에서 먼저 찾는다. 없으면 None — **생성하지 않는다.**"""
    ch = bucket(subject)
    key = _concept_key(concept)
    if not key:
        return None
    idx = _load_index(ch)
    # 파일명 우선 매칭 (block-lane, scan-arch 처럼 접두가 개념)
    for name, files in idx.items():
        if name.split("-")[0] == key or name == key:
            cand = files if isinstance(files, list) else [files]
            # 대안(-alt)은 뒤로 민다 — 기본 씬이 먼저 잡혀야 한다.
            for fn in sorted(cand, key=lambda f: ("-alt" in f, f)):
                p = os.path.join(_dir(ch), fn)
                if os.path.exists(p):
                    return p
    return None


def get_scene(subject, concept, motif=None, ratio="1:1"):
    """**라이브러리 우선.** 있으면 그 경로, 없으면 생성 지시서를 돌려준다.

    반환(찾음):   {"found": True,  "path": ..., "character": ...}
    반환(없음):   {"found": False, "prompt": ..., "save_as": ..., "concept": ..., "character": ...}

    없을 때 motif 를 안 주면 프롬프트를 만들 수 없으므로 에러를 낸다 —
    "생성해야 하는데 뭘 그릴지 안 정했다"를 조용히 넘기지 않는다.
    """
    ch = bucket(subject)

    hit = find_scene(subject, concept)
    if hit:
        return {"found": True, "path": hit, "character": ch, "concept": concept}

    if not motif:
        raise ValueError(f"'{concept}' 씬이 라이브러리에 없다. 생성하려면 motif 를 줘야 한다.")

    # 한글 개념어를 ascii 로만 걸러내면 이름이 통째로 비어 claudie_.png 가 된다.
    key = _concept_key(concept) or re.sub(r"[^0-9a-z가-힣]+", "-", concept.lower()).strip("-")
    if not key:
        raise ValueError(f"개념어에서 파일명을 만들 수 없다: {concept!r}")
    return {
        "found": False,
        "character": ch,
        "concept": concept,
        # no-text·스타일 고정부 그대로. ratio 만 구도 지시를 바꾼다(표지=4:5).
        "prompt": card.illust_prompt(subject, motif, ratio=ratio),
        "save_as": os.path.join(_dir(ch), f"{ch}_{key}.png"),
        "motif": motif,
        "ratio": ratio,
    }


def save_scene(order, src_png, note=None):
    """생성 결과를 라이브러리에 등록한다 — 파일 저장 + scenes.json + index.md 한 줄.

    order = get_scene() 이 돌려준 생성 지시서.
    """
    if order.get("found"):
        return order["path"]
    ch = order["character"]
    dst = order["save_as"]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.abspath(src_png) != os.path.abspath(dst):
        shutil.copyfile(src_png, dst)

    key = os.path.basename(dst)[len(ch) + 1:-4]
    idx = _load_index(ch)
    files = idx.setdefault(key, [])
    fn = os.path.basename(dst)
    if fn not in files:
        files.append(fn)
    _save_index(ch, idx)

    # index.md 표에 한 줄 — 사람이 읽는 정본도 같이 갱신한다.
    md = os.path.join(_dir(ch), "index.md")
    if os.path.exists(md):
        with open(md, encoding="utf-8") as f:
            t = f.read()
        row = (f"| `{fn}` | **{order['concept']}** | {order['concept']} | "
               f"{note or order.get('motif', '')[:60]} | {order.get('ratio', '1:1')} |\n")
        if fn not in t:
            t = t.replace("\n## 사용 이력", row + "\n## 사용 이력", 1)
            with open(md, "w", encoding="utf-8", newline="\n") as f:
                f.write(t)
    return dst


def rebuild_index(character):
    """폴더 실물에서 scenes.json 을 다시 만든다 (수동 정리 후 동기화용)."""
    idx = {}
    d = _dir(character)
    for fn in sorted(os.listdir(d)):
        m = re.match(rf"{character}_([a-z0-9\-]+?)(-alt)?\.png$", fn)
        if m:
            idx.setdefault(m.group(1), []).append(fn)
    _save_index(character, idx)
    return idx
