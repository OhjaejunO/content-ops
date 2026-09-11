# -*- coding: utf-8 -*-
"""발행로그.md → Episode 적재 (단방향 · 추가만).

**왜 이 방향인가.** README 「다음 — DB 정본화(`export_log`)」는 반대 방향(DB → 문서)을
적어 두었지만, 그 글은 2026-08-09 것이고 그 뒤에 **발행로그 쪽이 정본으로 굳었다** —
본사 정관 §2 예외 5 가 그 파일에만 쓰기를 열어 두었고, 발행 워커(`publish_tail.py`)가
인스타·Threads API 에서 **실측값**을 읽어 행을 적는다. 그래서 지금 어긋남의 꼴은
「문서가 DB 를 앞선다」 하나뿐이다 (2026-09-11 실측: DB 34건 · 발행로그 발행 편 51).

**단방향이다.** 이 명령은 **없는 편을 만들기만** 한다 — 기존 레코드의 값을 고치지도
지우지도 않는다. 문서가 DB 를 앞서는 것만 메우는 자리이고, 반대 방향(DB 가 앞섬)은
여기서 손대지 않고 **보고만** 한다. 고칠 곳이 하나여야 한다는 README 의 목적은 그대로다.

🔴 **기본값은 드라이런이다.** `--write` 를 명시하지 않으면 아무것도 안 넣는다.
🔴 **추측해서 넣지 않는다.** 발행일을 못 읽거나 카테고리를 모르면 그 편은 **건너뛰고
   왜 건너뛰었는지 적는다** — 모델이 「발행완료면 발행일이 있어야 한다」를 이미 걸고
   있고, 그것을 넘기려고 값을 지어내는 순간 DB 가 문서보다 나쁜 기록이 된다.

    py manage.py import_publog            # 드라이런 (무엇이 빠졌는지만)
    py manage.py import_publog --write
    py manage.py import_publog --self-test
"""
import datetime as dt
import os
import re

from django.core.management.base import BaseCommand

from ...models import Episode

PUBLOG = os.environ.get(
    "TOMANGCHI_PUBLOG",
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop\발행로그.md")

#: 제목 머리의 코너 이름 → 카테고리. **없는 꼴은 추측하지 않고 건너뛴다.**
CATEGORY = {
    "AI 소식": Episode.Category.AI_NEWS,
    "주간 AI 소식": Episode.Category.AI_NEWS,
    "기회": Episode.Category.OPPORTUNITY,
    "두드려봄": Episode.Category.HANDS_ON,
    "꿀팁": Episode.Category.TIP,
}
CORNER = re.compile(r"^\[([^\]]+)\]\s*(.*)$")
EPNO = re.compile(r"^ep(\d+)$")          # 🔴 `ep45-Threads`(재유통)는 같은 편이라 안 받는다
TS = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?")
KST = dt.timezone(dt.timedelta(hours=9))


def main_table(text):
    """본 표만. (발행로그에는 표가 넷이고, 경계는 **다음 구분선**이다.)"""
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines)
                  if ln.strip().startswith("| ep |") and "제목" in ln), None)
    if start is None:
        return ""
    end = len(lines) - 1
    for j in range(start + 2, len(lines)):
        if lines[j].strip().startswith("|---"):
            end = j - 2 if lines[j - 1].strip().startswith("|") else j - 1
            break
    return "\n".join(lines[start:end + 1])


def split_rows(text):
    """«| … |» 행. 🔴 **행은 여러 줄에 걸칠 수 있다** — 비고가 줄바꿈을 품는 행이 다섯이다."""
    out, buf = [], []
    for ln in text.split("\n"):
        s = ln.strip()
        if buf:
            if not s or s.startswith("|"):
                buf = []
            else:
                buf.append(s)
                if not s.endswith("|"):
                    continue
                s, buf = " ".join(buf), []
        if not s.startswith("|"):
            continue
        if not s.endswith("|"):
            buf = [s]
            continue
        cells = [c.strip() for c in s[1:-1].split("|")]
        if cells and all(c and set(c) <= set("-: ") for c in cells):
            continue
        out.append(cells)
    return out


def parse_rows(text):
    """발행로그 본 표 → `[{number, title, published_at, category, why}]`.

    `why` 가 차 있으면 **넣지 않는다** — 그 사유를 그대로 보고한다.
    """
    rows = split_rows(main_table(text))
    if not rows:
        return []
    head = rows[0]
    i_state = head.index("상태") if "상태" in head else 2
    i_date = head.index("발행일") if "발행일" in head else 3
    out = []
    for cells in rows[1:]:
        if len(cells) <= max(i_state, i_date):
            continue
        if re.sub(r"[*` ]", "", cells[i_state]) != "발행":
            continue
        key = re.sub(r"[*` ]", "", cells[0])
        m = EPNO.match(key)
        if not m:
            continue                      # 재유통 행(`-Threads`)·번호 미배정 행
        title = re.sub(r"\s+", " ", cells[1].strip().strip("*")).strip()
        rec = {"number": int(m.group(1)), "title": title[:200],
               "published_at": None, "category": None, "why": "",
               "date_only": False}
        c = CORNER.match(title)
        corner = c.group(1) if c else ""
        if corner in CATEGORY:
            rec["category"] = CATEGORY[corner]
        else:
            rec["why"] = "코너를 모른다: %s" % (corner or "(머리 없음)")
        t = TS.search(cells[i_date])
        if t:
            y, mo, d, h, mi = t.groups()
            rec["published_at"] = dt.datetime(int(y), int(mo), int(d),
                                              int(h or 0), int(mi or 0), tzinfo=KST)
            # 🔴 시각이 없는 옛 행은 날짜만 참이다 — 00:00 은 자리표시이지 실측이 아니라고
            #    화면에 같이 찍는다. 모델이 발행일을 요구해서 넣는 값이고, 그 사정을
            #    적어 두지 않으면 다음 사람이 «00:00 에 올렸다» 로 읽는다.
            rec["date_only"] = h is None
        elif not rec["why"]:
            rec["why"] = "발행일이 시각 꼴이 아니다: %s" % cells[i_date][:24]
        out.append(rec)
    return out


class Command(BaseCommand):
    help = "발행로그.md 의 «발행» 편 중 DB 에 없는 것을 만든다 (단방향·추가만)"

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true",
                            help="실제로 넣는다 (없으면 드라이런)")
        parser.add_argument("--publog", default=PUBLOG)
        parser.add_argument("--self-test", action="store_true")

    def handle(self, *args, **opts):
        if opts["self_test"]:
            return self._self_test()
        path = opts["publog"]
        if not os.path.exists(path):
            self.stdout.write("STATUS: FAIL no-publog %s" % path)
            return
        with open(path, encoding="utf-8") as f:
            recs = parse_rows(f.read())
        have = dict(Episode.objects.values_list("number", "status"))
        missing = [r for r in recs if r["number"] not in have]
        skipped = [r for r in missing if r["why"]]
        addable = [r for r in missing if not r["why"]]
        # 🔴 반대 방향은 고치지 않고 **보고만** 한다.
        orphan = sorted(set(have) - {r["number"] for r in recs})

        self.stdout.write("발행로그 «발행» 편 %d · DB %d · 없는 편 %d"
                          % (len(recs), len(have), len(missing)))
        for r in skipped:
            self.stdout.write("  건너뜀 ep%-3d %s" % (r["number"], r["why"]))
        if orphan:
            self.stdout.write("  🔴 DB 에만 있는 편(문서에 없음 · 손대지 않는다): %s"
                              % ", ".join("ep%d" % n for n in orphan))
        made = 0
        for r in addable:
            line = "ep%-3d %s · %s%s" % (
                r["number"], r["title"][:40],
                r["published_at"].strftime("%Y-%m-%d %H:%M"),
                " (시각 없는 행 — 00:00 은 자리표시)" if r["date_only"] else "")
            if not opts["write"]:
                self.stdout.write("  넣을 것 %s" % line)
                continue
            Episode(number=r["number"], title=r["title"], category=r["category"],
                    status=Episode.Status.PUBLISHED,
                    published_at=r["published_at"]).save()
            made += 1
            self.stdout.write("  넣음   %s" % line)
        self.stdout.write("STATUS: OK (%d편 %s · 건너뜀 %d)"
                          % (made if opts["write"] else len(addable),
                             "넣음" if opts["write"] else "넣을 것", len(skipped)))

    # ── 역검증 (§0) ─────────────────────────────────────────────────────────
    def _self_test(self):
        doc = "\n".join([
            "| ep | 제목 | 상태 | 발행일 | 비고 |",
            "|---|---|---|---|---|",
            "| **ep90** | [AI 소식] 제목 하나 | **발행** | **2026-09-07 15:06 KST** | — |",
            "| **ep90-Threads** | 같은 편 · 재유통 | **발행** | **2026-09-07 19:00 KST** | — |",
            "| **ep91** | [기회] 두 번째 | **발행** | 2026-09-08 | 비고가",
            "여러 줄이다 |",
            "| **ep92** | [알 수 없는 코너] 세 번째 | **발행** | **2026-09-09 10:00 KST** | — |",
            "| **ep93** | [AI 소식] 날짜 없음 | **발행** | **미확인** | — |",
            "| **ep94** | [AI 소식] 아직 | 제작완료 | — | — |",
            "| **ep95** | [AI 소식] 취소됨 | **발행취소** | — | — |",
            "",
            "## 누적 수치 — **2편 / 3건**",
            "",
            "| 층 | 값 |",
            "|---|---|",
            "| 편수 | 2 |"])
        got = {r["number"]: r for r in parse_rows(doc)}
        bad = 0

        def case(label, cond, detail=""):
            nonlocal bad
            bad += 0 if cond else 1
            self.stdout.write("  %s %-54s %s" % ("OK  " if cond else "FAIL", label, detail))

        case("«발행» 행만 읽는다 (제작완료·발행취소는 뺀다)",
             set(got) == {90, 91, 92, 93}, "%s" % sorted(got))
        case("🔴 재유통 행(`-Threads`)은 같은 편이라 안 받는다", 90 in got and len(got) == 4)
        case("시각까지 읽어 KST 로 둔다",
             got[90]["published_at"] == dt.datetime(2026, 9, 7, 15, 6, tzinfo=KST),
             "%s" % got[90]["published_at"])
        case("코너 → 카테고리", got[90]["category"] == Episode.Category.AI_NEWS
             and got[91]["category"] == Episode.Category.OPPORTUNITY)
        case("여러 줄 행도 읽는다 (종전 파서가 통째로 빠뜨리던 꼴)",
             got[91]["published_at"] == dt.datetime(2026, 9, 8, 0, 0, tzinfo=KST))
        case("🔴 모르는 코너는 추측하지 않고 건너뛴다", bool(got[92]["why"]), got[92]["why"])
        case("🔴 발행일을 못 읽으면 건너뛴다 (모델이 요구하는 값을 지어내지 않는다)",
             bool(got[93]["why"]), got[93]["why"])
        case("다른 표의 행은 안 섞인다 (누적 수치 표)", 2 not in got)
        self.stdout.write("STATUS: %s" % ("OK" if not bad else "FAIL self-test %d건" % bad))
