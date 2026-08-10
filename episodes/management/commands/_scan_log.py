"""아침 스캔 로그(`YYYY-MM-DD.md`)에서 후보를 읽는다.

로그 형식이 아직 굳지 않아 **엄격하게 파싱하지 않는다.** 정규식을 조이면 다음
로그가 조금만 달라져도 못 읽고, 그러면 사람이 다시 손으로 옮기게 된다.

읽는 곳은 두 군데다.
- **목록**: '후보'가 들어간 제목 아래의 `- ` / `1. ` 항목.
- **표**: 첫 열 머리글에 '후보'가 든 마크다운 표의 첫 열. 제목과 무관하게 읽는다 —
  실제 로그의 후보 표는 `## 판정 요약` 처럼 '후보'가 없는 제목 아래에 있다.

표를 읽지 않던 시절에는 후보가 표로 적힌 로그를 통째로 못 읽었다. 같은 후보가
여러 표에 나오는 것이 정상이므로(판정 요약 · scan_check 실측 · 자동 스캔 섹션)
**순서를 지키며 중복만 제거한다.**

못 읽으면 **조용히 빈 목록을 돌려주지 않는다.** 무엇을 못 읽었는지와 수동 입력
방법을 같이 알려야 사람이 다음 수를 정할 수 있다.

이름이 `_` 로 시작해 Django 명령 탐색에서 제외된다.
"""
import os
import re

#: 목록 항목: `- 후보`, `* 후보`, `1. 후보`
ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$')
HEADING = re.compile(r'^\s*(#+)\s*(.*\S)\s*$')
#: 표 구분선: `|---|---|`, `|:---:|---:|`
TABLE_RULE = re.compile(r'^\s*\|(?:\s*:?-{2,}:?\s*\|)+\s*$')


class ScanLogError(Exception):
    """읽기 실패. 메시지를 그대로 사용자에게 보여준다."""


def log_path(log_dir, date_str):
    if not log_dir:
        raise ScanLogError(
            '스캔 로그 폴더가 설정되지 않았습니다.\n'
            '  환경변수 SCAN_LOG_DIR 에 스캔로그 폴더 경로를 넣으세요.\n'
            '  예) SCAN_LOG_DIR=C:\\...\\tomangchi-lab.github.io\\workshop\\스캔로그\n'
            '  설정 없이 쓰려면 후보를 인자로 직접 넘기세요: '
            'python manage.py scan_check "후보1" "후보2"')

    path = os.path.join(log_dir, f'{date_str}.md')
    if not os.path.isfile(path):
        raise ScanLogError(
            f'스캔 로그가 없습니다: {path}\n'
            '  날짜를 지정하려면 --from-log YYYY-MM-DD 로 주세요.\n'
            '  로그 없이 쓰려면 후보를 인자로 직접 넘기세요.')
    return path


def _row_cells(line):
    """표 행이면 셀 목록, 아니면 None."""
    text = line.strip()
    if not text.startswith('|'):
        return None
    text = text[1:]
    if text.endswith('|'):
        text = text[:-1]
    return [cell.strip() for cell in text.split('|')]


def _list_candidates(lines):
    """'후보' 제목 아래의 목록 항목. (섹션을 찾았는지, 항목들) 을 돌려준다.

    같은 깊이 이하의 다음 제목을 만나면 멈춘다.
    """
    depth = None
    found_section = False
    items = []

    for line in lines:
        heading = HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            if depth is not None and level <= depth:
                break                       # 섹션 끝
            if depth is None and '후보' in title:
                depth, found_section = level, True
            continue
        if depth is None:
            continue
        item = ITEM.match(line)
        if item:
            items.append(_clean(item.group(1)))

    return found_section, items


def _table_candidates(lines):
    """첫 열 머리글에 '후보'가 든 표의 첫 열.

    제목은 보지 않는다 — 실제 로그의 후보 표는 '후보'가 들어가지 않은 제목
    아래에 있다. 표를 가르는 것은 머리글 자신이다.
    """
    items = []
    index = 0
    total = len(lines)

    while index < total:
        cells = _row_cells(lines[index])
        is_header = (
            cells
            and index + 1 < total
            and TABLE_RULE.match(lines[index + 1])
            and '후보' in _clean(cells[0])
        )
        if not is_header:
            index += 1
            continue

        index += 2                          # 머리글 + 구분선을 건너뛴다
        while index < total:
            row = _row_cells(lines[index])
            if not row or TABLE_RULE.match(lines[index]):
                break
            value = _clean(row[0])
            if value:
                items.append(value)
            index += 1

    return items


def parse_candidates(text):
    """'후보' 목록과 후보 표를 함께 읽는다. 순서를 지키며 중복만 제거한다."""
    lines = text.splitlines()
    found_section, items = _list_candidates(lines)
    table_items = _table_candidates(lines)

    seen = set()
    candidates = []
    for value in items + table_items:
        if value not in seen:
            seen.add(value)
            candidates.append(value)

    if not found_section and not table_items:
        raise ScanLogError(
            "로그에서 '후보' 섹션도 후보 표도 찾지 못했습니다.\n"
            "  `## 후보` 같은 제목 아래에 목록으로 적어주세요:\n"
            '    ## 후보\n    - 소재 한 줄\n    - 소재 한 줄\n'
            '  또는 첫 열 머리글이 `후보` 인 표로 적어주세요:\n'
            '    | 후보 | 판정 |\n    |---|---|\n    | 소재 한 줄 | 채택 |\n'
            '  또는 후보를 인자로 직접 넘기세요.')
    if not candidates:
        raise ScanLogError(
            "'후보' 섹션은 찾았지만 읽을 항목이 없습니다.\n"
            '  `- ` 로 시작하는 목록이나, 첫 열 머리글이 `후보` 인 표로 적어주세요.')
    return candidates


def _clean(text):
    """마크다운 강조·링크 껍데기만 벗긴다. 내용은 그대로 둔다."""
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)    # [텍스트](링크)
    text = re.sub(r'[*_`]{1,3}', '', text)
    return text.strip()


def read_candidates(log_dir, date_str):
    path = log_path(log_dir, date_str)
    with open(path, encoding='utf-8') as fh:
        return parse_candidates(fh.read()), path
