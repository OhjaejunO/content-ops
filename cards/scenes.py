# -*- coding: utf-8 -*-
"""씬 라이브러리 — 재사용이 먼저, 생성은 없을 때만.

크레딧이 드는 것은 생성뿐이다. 그래서 이 모듈의 기본 동작은 **찾기**이고,
생성은 못 찾았을 때만 일어난다. 호출부가 순서를 뒤집을 수 없도록
`get_scene()` 하나로 묶어 두었다.

**등재 단위는 포즈가 아니라 상황이다 (2026-08-15 확정).**
개념명도 상황 기준으로 적는다 — `login-and-work` · `shared-computer` · `two-tests`
처럼. `explain` · `point` · `surprise` 같은 **포즈명은 등재하지 않는다**
(`RETIRED_CONCEPTS` 참조). 재사용은 **개념이 반복될 때** 성립한다. 차단·검사·통과처럼
여러 편에 걸쳐 같은 개념이 나오는 것은 재사용 대상이지만, 포즈는 매 편 상황이 달라
애초에 재사용 대상이 아니다.

**`find_scene` 이 히트해도 그것으로 끝이 아니다.** 개념이 같아도 이번 카드의 상황과
다르면 **새로 생성한다.** 재사용은 크레딧 절약 수단이지 목적이 아니다. 안 맞는 씬을
재사용해 크레딧을 아끼면, 캐릭터가 서 있기만 하는 카드가 나오고 그건 그 카드에
일러스트가 없는 것과 같다 (ep16 1차 제작에서 02·04·07 이 전부 그렇게 됐다).

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
    # 카드 슬롯 개념 — 포즈가 아니라 자리다. 표지는 편마다 반드시 하나 있다.
    "cover": ["표지", "커버", "cover"],
    # ── 상황 씬 (2026-08-15 신설) ─────────────────────────────────────
    # 포즈가 아니라 **카드 본문이 말하는 상황**을 그린 씬. 범용 포즈만 쓰면 설명 카드가
    # 서로 같은 그림이 되어 캐러셀에서 구분이 안 된다(ep16 1차 제작에서 실제로 났다).
    # 소재는 달라도 구조가 같은 소식에 그대로 재사용된다 — 예를 들어 `two-tests` 는
    # 벤치마크가 갈리는 어떤 모델 소식에도 맞는다.
    "login-and-work": ["로그인해서 일함", "대신 일함", "무인 작업", "자리 비움",
                       "login-and-work"],
    "two-tests": ["두 시험", "시험 두 종류", "순위 뒤집힘", "일장일단", "two-tests"],
    "shared-computer": ["컴퓨터 공유", "한 대 공유", "공유 컴퓨터", "권한 공유",
                        "shared-computer"],
    "handoff": ["인계", "넘겨줌", "결과물 전달", "handoff"],
    # ⚠️ **키워드는 부분 문자열로 매칭되고 먼저 선언된 개념이 이긴다.**
    #    그래서 "마감 겹침" 으로 부르면 위쪽 `deadline`("마감")이 먼저 잡혀 엉뚱한
    #    파일명이 나온다. 아래 개념은 **"겹침"** 으로 부를 것. 새 개념을 넣을 때는
    #    쓰려는 호출 문자열이 위 개념의 키워드를 품고 있지 않은지 먼저 확인한다.
    #
    # ep15(마누스) — 기간·마감이 얽힌 소식의 상황 4종. 서비스가 달라도 구조가 같으면
    # 그대로 맞는다: 무료 개방 이벤트, 창이 겹치는 일정, 점검으로 막히는 기간, 이관 마감.
    "deadline-overlap": ["기간 겹침", "겹침", "두 기간", "창이 겹침",
                         "deadline-overlap", "overlap"],  # «마감 겹침»은 위 deadline("마감")에 먼저 걸리는 죽은 키워드라 뺐다 (self_test 2026-08-19)
    # 2026-08-27: «무료 개방»·«free» 를 뺐다 — 이 PR 이 열려 있던 사이(8/26) 등재된
    # `free-lane-more-items`(ep33) 가 그 둘을 키워드로 쓴다. 이 표는 **먼저 선언된 개념이 이기므로**
    # 그대로 두면 `무료 개방`·`free`·`free-lane` 호출이 전부 이쪽으로 와 ep33 씬을 가린다
    # (self_test 실측 3건). 먼저 선언된 쪽이 정본이고, 이 개념은 «무료 풀림»으로 부른다.
    # 🔴 «개방» 도 뺀다 — 매칭이 **부분 문자열**이라 «개방» 하나만 남겨도 «무료 개방» 호출을 그대로 삼킨다
    #    (키워드를 지운 1차 수정에서 실측: 충돌 3건 → 1건, «무료 개방» 은 여전히 free-open 으로 갔다).
    #    남은 부름말: 무료 풀림 · 요금 면제 · 공짜 · free-open.
    "free-open": ["무료 풀림", "요금 면제", "공짜", "free-open"],
    "shutter": ["셔터", "못 씀", "닫힘", "점검", "일시 중단",
                "shutter", "closed"],  # «접근 차단 기간»은 block("차단")에 먼저 걸리는 죽은 키워드라 뺐다 (self_test 2026-08-19)
    "backup": ["백업", "옮겨 담기", "대피", "보관", "이관", "backup"],
    # ── 지피(OpenAI) 상황 씬 — 속도·등급·측정조건 계열 (2026-08-15 신설) ──────
    # 울트라패스트 편에서 6장을 생성해 놓고 **여기 등재를 빠뜨렸다.** 파일과
    # scenes.json 은 멀쩡한데 `_concept_key` 가 None 을 돌려 `find_scene` 이
    # 영원히 못 찾는 상태였다 — 다음 편이 같은 그림을 다시 생성한다.
    # 저장을 막는 가드(`get_scene`)는 있었지만 그 가드를 **거치지 않고** 저장하면
    # 그만이라, 이번엔 `self_test()` 로 «색인에서 되찾아지는가»를 직접 본다.
    #
    # ⚠️ 순서가 판정을 바꾼다 — 먼저 걸리는 항목이 이긴다(`_SUBJECT_MAP` 과 같은 규칙).
    # `different-start-lines` 를 `two-clocks` 보다 **앞에** 둔다. 뒤에 두면
    # "비교 조건" 이 two-clocks 의 "비교" 에 먼저 걸려 엉뚱한 씬이 잡힌다.
    "same-brain-faster-hands": ["속도", "가속", "빠름", "지연", "실시간", "저지연",
                                "speed", "faster", "latency"],
    "same-box-express-tag": ["등급", "티어", "서비스 등급", "옵션", "같은 모델",
                             "tier", "service tier"],
    "different-start-lines": ["측정 조건", "비교 조건", "기준이 다름", "출발선",
                              "공정하지 않음", "다른 날", "baseline", "conditions"],
    "two-clocks": ["시간", "소요", "몇 시간", "비교", "벤치마크", "완주",
                   "duration", "elapsed"],
    "thinks-longer-vs-answers-faster": ["혼동", "구분", "갈림길", "모드 차이",
                                        "이름이 비슷", "ultra", "오래 생각"],
    "narrow-door": ["제한", "프리뷰", "초대제", "대기", "일부 고객", "미공개",
                    "preview", "limited", "waitlist"],
    # ── 소품 상황 씬 — 「같은 것을 다르게 적어 놓았다」 계열 (2026-08-16 신설) ──
    # 로스터 밖 주체(ByteDance·Higgsfield 등) 소식에 쓰는 `props` 버킷용이다.
    # 소재는 씨댄스 2.5 지만 **구조가 같은 소식에 그대로 재사용된다** — 판매면과
    # API 문서와 changelog 가 같은 사양을 다르게 적는 일은 어느 도구에나 있다.
    #
    # 두 개념을 나눈 이유: 표지(붙어 있는 상태)와 코멘트(떼어 놓고 견주는 상태)는
    # **같은 상황의 다른 국면**이라 그림이 달라야 한다. 하나로 묶으면 두 카드가
    # 같은 그림이 되고, 그게 ep16 에서 났던 사고다(§6.8).
    #
    # ⚠️ 키워드에 「설명」·「비교」를 쓰지 않는다. 앞선 개념 `explain`·`two-clocks` 가
    # 그 두 글자를 이미 갖고 있어 **먼저 걸린다.** 처음에 «설명이 다름»·«나란히 비교»로
    # 적었다가 `self_test` 가 충돌 5건으로 잡아냈다 — None 이 아니라 엉뚱한 씬이
    # 잡히는 쪽이라 그대로 뒀으면 카드에 다른 그림이 실렸을 것이다.
    "same-thing-three-labels": ["말이 다름", "표기가 갈림", "같은 것 다른 이름",
                                "제각각", "저마다 다르게", "different-labels"],
    # ep32 (2026-08-26) — 두 자리(챗·Cowork)가 같은 수첩(메모리)을 쓴다
    # ep33 (2026-08-26) — 무료 차로가 열려 더 많은 것을 들고 지나간다(무료로 되는 것 모음)
    "free-lane-more-items": ["무료 개방", "무료로 되는 것", "무료 차로", "무료 확대", "free", "free-lane", "free-lane-more-items"],
    "one-notebook-two-desks": ["기억 공유", "메모리 공유", "같은 수첩", "두 자리 한 기억", "하나의 메모리", "memory", "shared-memory", "one-notebook-two-desks"],
    # ep34 (2026-08-26) — 다음 세대 설계도를 먼저 펼쳐 보인다(Qwen4 구조 미리보기 오픈 웨이트)
    "blueprint-unroll": ["설계도 공개", "구조 미리보기", "청사진", "차세대 구조", "선행 공개", "blueprint", "blueprint-unroll"],   # «architecture-preview» 제거 2026-08-27 — 위 narrow-door 의 «preview» 에 먼저 걸리는 죽은 키워드였다(main 단독 self_test 에서도 잡히던 기존 결함)
    "three-labels-laid-out": ["나란히 놓기", "펼쳐 놓기", "층별 정리", "대조표",
                              "견주기", "laid-out", "side-by-side"],
    # ep35 (2026-08-27) — 이름 없이 돌던 것에 이름표와 가격표가 같이 붙는다
    # («공짜»·«무료 개방» 은 위 free-open·free-lane-more-items 가 이미 가진다 —
    #  여기는 «무료였다가 값이 붙은» 전환이라 키워드를 겹치지 않게 잡았다)
    "unmasked-and-priced": ["정체 공개", "익명 해제", "이름표 붙음", "값이 붙음",
                            "유료 전환", "unmasked", "unmasked-and-priced"],
    # ep36 (2026-08-27) — 말하면 그 자리에서 정리된 글이 된다(받아쓰기·필러 제거)
    "speak-and-it-writes": ["받아쓰기", "음성 입력", "말하면 글", "구술",
                            "필러 제거", "speak-and-it-writes"],
    # ep37 (2026-08-27) — 잘못을 알아차린 쪽이 리포트 초안을 스스로 쓴다
    "drafts-own-report": ["리포트 초안", "스스로 신고", "초안 작성",
                          "잘못 알아차림", "drafts-own-report"],
    # ep38 (2026-08-27) — 한 장 뽑는 값이 동전 한 닢이다(장당 정액 과금)
    "penny-a-picture": ["장당 요금", "한 장 값", "동전 한 닢", "낱장 과금",
                        "penny-a-picture"],
    # ── ep40 (2026-08-31) — OpenClaw 2.0. 넷 다 **구조가 같은 소식에 재사용된다.** ──
    # 🔴 키워드 충돌은 눈으로 훑지 않고 기계로 봤다 — 부를 문자열을 실제로 넣어
    #    ① 기존 개념에 먼저 걸리는가 ② 새 키워드끼리 잡아먹는가 ③ 기존 키워드가 새
    #    개념 이름에 걸리는가 세 축 24케이스. 전부 통과.
    # 새로 설치할 때 이미 그 컴퓨터에 있는 것(구독·키·로컬 모델)에서 시작한다
    "already-on-your-desk": ["이미 있는 것", "있던 것으로", "가진 것부터",
                             "already-on-your-desk"],
    # 배경에서 기억을 추리되 **출처가 확인된 것만** 위 칸으로 올린다
    "only-labeled-moves-up": ["표 붙은 것만", "골라 올림", "확인된 것만",
                              "only-labeled-moves-up"],
    # 손목·손안·회의실 — 에이전트가 화면 밖의 기기와 자리로 나간다
    "wrist-hand-and-room": ["손목과 손안", "기기 셋", "밖으로 나감",
                            "wrist-hand-and-room"],
    # 닫힌 통로인데 이음매 한 곳에서 밖으로 샌다 — «잃음»이 아니라 «나감»이다.
    # 🔴 `drop`(유실)과 다르다. 그쪽은 떨어져 사라지고, 이쪽은 **남은 채 밖에 놓인다.**
    #    07 카드의 셋(건강 요약이 모델 회사까지 감 · 되감아도 파일은 그대로 · 팀 역할이
    #    사람을 못 가둠)이 전부 «잃는» 이야기가 아니라서 `drop` 재사용이 반려됐다.
    "sealed-pipe-one-seam": ["이음매", "한 곳으로 샘", "새는 자리",
                             "sealed-pipe-one-seam"],
}

#: **사용 보류된 «포즈» 개념 (2026-08-15).** 등재 단위를 잘못 잡은 흔적이다.
#:
#: 처음에는 `explain` · `point` · `surprise` 같은 포즈를 등재하고 "소재와 무관한 순수
#: 포즈라 편이 바뀌어도 그대로 재사용된다"고 적어 두었다. **그 전제가 틀렸다.**
#: ep16 1차 제작에서 02·04·07 이 전부 "그로키가 서 있는 비슷한 사진"이 됐고, 카드
#: 본문이 말하는 상황을 그림이 하나도 보여주지 못했다. 어느 카드에나 맞는 그림은
#: **어느 카드에도 딱 맞지 않는다.**
#:
#: 재사용은 **개념이 반복될 때** 의미가 있다 — 차단·검사·통과·승인 관문처럼 여러 편에
#: 걸쳐 같은 개념이 나온다. 포즈는 매 편 상황이 달라서 애초에 재사용 대상이 아니다.
#:
#: 파일은 라이브러리에 **남기되 조회에서 제외**한다. 상황 씬으로 대체되면 지운다.
RETIRED_CONCEPTS = {
    "explain": ["설명", "설명하기", "안내", "말하기", "explain", "presenting"],
    "point": ["가리키기", "가리킴", "지목", "시선", "point", "pointing"],
    "surprise": ["놀람", "놀라기", "충격", "의외", "surprise", "shocked"],
    "arms": ["팔짱", "단호", "경고", "arms-crossed", "firm"],
    "tilt": ["갸웃", "의문", "헷갈림", "tilt", "puzzled"],
}


def bucket(subject):
    """씬이 들어갈 폴더 키. 로스터 밖 주체는 전부 `props` 로 모인다.

    캐릭터에 `folder` 가 있으면 그것을 쓴다 — 리디자인된 캐릭터가 구판 씬과 한 폴더에
    섞이지 않게 하기 위해서다(클로디 v2, 2026-08-19). 없으면 키가 곧 폴더다.
    """
    key = card.pick_character(subject)
    if not key:
        return PROPS
    return card.CHARACTERS[key].get("folder", key)


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


def _concept_key(concept, table=None):
    """한국어·영어 개념어를 라이브러리 키로 정규화한다.

    `table` 은 `self_test()` 가 합성 표를 넣어 보기 위한 자리다 — 평소엔 비운다.
    """
    if table is None:
        _ensure_self_test()      # 실물 표를 쓸 때만. 합성 표(self_test)는 검사 대상이 아니다.
    t = CONCEPTS if table is None else table
    c = (concept or "").strip().lower()
    if c in t:
        return c
    for key, words in t.items():
        if any(w in c for w in words):
            return key
    return None


def _retired_key(concept):
    """사용 보류된 포즈 개념이면 그 키를 돌려준다. 아니면 None."""
    c = (concept or "").strip().lower()
    if c in RETIRED_CONCEPTS:
        return c
    for key, words in RETIRED_CONCEPTS.items():
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


def get_scene(subject, concept, motif=None, ratio="1:1", place=None, staging=None):
    """**라이브러리 우선.** 있으면 그 경로, 없으면 생성 지시서를 돌려준다.

    반환(찾음):   {"found": True,  "path": ..., "character": ...}
    반환(없음):   {"found": False, "prompt": ..., "save_as": ..., "concept": ..., "character": ...}

    staging (2026-08-19~) = `card.Staging` — 공간·소품·행동·무드·포맷을 소재에서 정한 연출 층.
    **새 편은 staging 을 준다.** place/motif 는 옛 호환 경로다(사무실·따뜻한 낮 고정 무대).

    없을 때 motif 를 안 주면 프롬프트를 만들 수 없으므로 에러를 낸다 —
    "생성해야 하는데 뭘 그릴지 안 정했다"를 조용히 넘기지 않는다.
    """
    ch = bucket(subject)

    hit = find_scene(subject, concept)
    if hit:
        return {"found": True, "path": hit, "character": ch, "concept": concept}

    if not motif and staging is None:
        raise ValueError(f"'{concept}' 씬이 라이브러리에 없다. 생성하려면 staging(또는 옛 motif)을 줘야 한다.")

    # CONCEPTS 에 없으면 **저장 자체를 막는다.**
    # 종전에는 한글 개념어를 그대로 슬러그로 써서 `groki_로그인해서-일함.png` 같은
    # 파일을 만들었다. 그런데 `_load_index` 의 정규식은 `[a-z0-9\-]` 만 받는다 —
    # 한글 파일명은 색인에 **영원히 안 잡힌다.** 저장은 되는데 조회가 안 되니
    # 다음 편이 같은 씬을 또 생성한다. 조용히 새는 크레딧이라 여기서 끊는다.
    retired = _retired_key(concept)
    if retired:
        raise ValueError(
            f"'{concept}' 는 **포즈** 개념이라 사용 보류다 (RETIRED_CONCEPTS: {retired}). "
            f"등재 단위는 포즈가 아니라 **상황**이다 — 카드 본문이 말하는 장면을 개념명으로 "
            f"잡아라 (login-and-work · shared-computer · two-tests 처럼). "
            f"포즈로 만들면 어느 카드에나 맞지만 어느 카드에도 딱 맞지 않는 그림이 나온다."
        )

    key = _concept_key(concept)
    if not key:
        raise ValueError(
            f"'{concept}' 는 CONCEPTS 에 없다. scenes.CONCEPTS 와 해당 캐릭터의 "
            f"index.md 에 먼저 등재할 것 — 등재 없이 저장하면 색인에 안 잡히는 "
            f"파일이 쌓인다."
        )
    return {
        "found": False,
        "character": ch,
        "concept": concept,
        # no-text·스타일 고정부 그대로. ratio 만 구도 지시를 바꾼다(표지=4:5).
        "prompt": card.illust_prompt(subject, motif, ratio=ratio, place=place, staging=staging),
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
        # «장면» 열은 **실물**을 적는다 — 의도가 아니다. 여기에 motif(생성 의도)를
        # 넣으면 색인이 거짓말을 하고, `find_scene` 이 그 거짓말을 그대로 재사용해
        # 카드에 잘못된 그림이 규칙을 지킨 채로 실린다 (2026-08-14 클로디 폴더 실제 사고).
        # 그래서 note 가 없을 때 motif 로 때우지 않는다 — 채워야 한다는 표시를 남긴다.
        if note:
            scene = note
        else:
            scene = "⚠️ 실물 미기록 — 그림을 열어 보이는 대로 채울 것"
            print(f"[scenes] {fn}: note= 없이 저장했다. «장면» 열은 실물을 적어야 한다.")
        row = (f"| `{fn}` | **{order['concept']}** | {order['concept']} | "
               f"{scene} | {order.get('ratio', '1:1')} |\n")
        if fn not in t:
            t = t.replace("\n## 사용 이력", row + "\n## 사용 이력", 1)
            with open(md, "w", encoding="utf-8", newline="\n") as f:
                f.write(t)
    return dst


# ── 색인 자기검사 ────────────────────────────────────────────────────
# 이 라이브러리의 유일한 존재 이유는 **다시 찾아지는 것**이다. 찾아지지 않으면
# 파일이 아무리 잘 쌓여도 다음 편이 같은 그림을 다시 생성한다 — 크레딧이 조용히
# 샌다(정관 §0 «조용히 실패하는 코드»). 그래서 «등재된 말이 자기 개념으로
# 되돌아오는가»를 코드가 직접 본다.
#
# 잡는 것은 두 가지다.
#   ① 미등재 — `_concept_key` 가 None. 저장은 되는데 조회가 안 되는 상태.
#   ② 그림자 — 앞선 개념의 키워드가 뒤 개념의 말을 먼저 삼킨다. 이쪽이 더 고약하다.
#      **None 이 아니라 «엉뚱한 그림»이 잡히므로** 규칙을 지킨 채 잘못된 씬이 실린다.


def _shadow_check(table):
    """`[(개념, 종류, 입력, 실제)]` — 비어 있으면 표가 자기일관적이다."""
    bad = []
    for key, words in table.items():
        got = _concept_key(key, table)
        if got != key:
            bad.append((key, "슬러그", key, got))
        for w in words:
            got = _concept_key(w, table)
            if got != key:
                bad.append((key, "키워드", w, got))
    return bad


#: 역검증 — **일부러 그림자를 만든 표.** 반드시 걸려야 한다.
#: 이게 없으면 `_shadow_check` 가 늘 빈 목록을 돌려주는 고장이라도 «통과»로 읽힌다.
#: `비교` 가 앞에 있어 뒤 개념의 `비교 조건` 을 삼키는 형태 — 실제로 이번에
#: 순서를 잘못 두면 났을 바로 그 충돌이다.
_SHADOW_FIXTURE = {
    "two-clocks": ["비교"],
    "different-start-lines": ["비교 조건"],
}


def self_test():
    """`(정상표_실패목록, 역검증_통과여부)`."""
    live = _shadow_check(CONCEPTS)
    caught = _shadow_check(_SHADOW_FIXTURE)
    return live, bool(caught)


_SELF_TEST_DONE = False


def _ensure_self_test():
    """개념 표를 쓰기 **전에** 그림자 검사를 한 번 돌린다. 그림자가 있으면 시작하지 않는다.

    🔴 **왜 자동 호출인가 (2026-08-27).** `self_test()` 는 8/26 부터 열흘 동안 **아무도 부르지 않았다.**
    그 사이 ep33 `free-lane-more-items` 의 «무료 개방» 이 뒤에 선언된 개념에 가려졌고, ep34
    `blueprint-unroll` 의 «architecture-preview» 는 `narrow-door` 의 «preview» 에 먹혔다.
    둘 다 **조용히** 다른 씬을 돌려주는 상태였다 — 검사가 있었는데 부르는 자리가 없었다.
    부르는 자리가 없는 검사는 검사가 아니라 메모다(정관 §0 «감지 장치가 값을 담는지»).

    `cardcheck._ensure_self_test()` 와 같은 방식이다 — 한 프로세스에서 한 번만 돌고(0.001초대),
    실패하면 **예외로 멈춘다.** 조용히 넘어가면 이 함수의 존재 이유가 없다.
    """
    global _SELF_TEST_DONE
    if _SELF_TEST_DONE:
        return
    live, caught = self_test()
    if live:
        raise AssertionError(
            "씬 개념 키워드 그림자 %d건 — 먼저 선언된 개념이 뒤 개념의 부름말을 삼킨다: %s\n"
            "고치는 법: 가리는 쪽 키워드를 빼거나(부분 문자열까지 본다) 선언 순서를 옮긴다. "
            "`py cards/scenes.py` 로 재측정(그 진입점이 자기검사를 찍는다)." % (len(live), live))
    if not caught:
        raise AssertionError("그림자 역검증이 헛돈다 — _SHADOW_FIXTURE 가 안 걸린다. 검사기가 고장 났다.")
    _SELF_TEST_DONE = True


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


if __name__ == "__main__":
    import io as _io
    import sys as _sys

    # 콘솔 코드페이지가 cp949 라 한글·em dash 가 그대로는 못 찍힌다.
    _sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8",
                                    errors="replace")

    live, caught = self_test()
    print("[색인 자기검사]")
    for key, kind, val, got in live:
        print(f"  FAIL {key:32} {kind} {val!r} -> {got}")
    print(f"  {'OK  ' if not live else 'FAIL'} 정상표 — 개념 {len(CONCEPTS)}개, "
          f"충돌 {len(live)}건")
    print(f"  {'OK  ' if caught else 'FAIL'} 역검증 — 일부러 만든 그림자를 "
          f"{'잡았다' if caught else '못 잡았다 (검사가 헛돈다)'}")
    _sys.exit(0 if not live and caught else 1)
