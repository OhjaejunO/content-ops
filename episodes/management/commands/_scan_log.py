"""아침 스캔 로그(`YYYY-MM-DD.md`)에서 후보를 읽는다.

로그 형식이 아직 한 건뿐이라 **엄격하게 파싱하지 않는다.** 형식이 굳기 전에
정규식을 조이면 다음 로그가 조금만 달라져도 못 읽고, 그러면 사람이 다시 손으로
옮기게 된다. 그래서 "'후보'가 들어간 제목 아래의 목록 항목"까지만 보고
나머지는 건드리지 않는다.

못 읽으면 **조용히 빈 목록을 돌려주지 않는다.** 무엇을 못 읽었는지와 수동 입력
방법을 같이 알려야 사람이 다음 수를 정할 수 있다.

이름이 `_` 로 시작해 Django 명령 탐색에서 제외된다.
"""
import os
import re

#: 목록 항목: `- 후보`, `* 후보`, `1. 후보`
ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$')
HEADING = re.compile(r'^\s*(#+)\s*(.*\S)\s*$')


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


def parse_candidates(text):
    """'후보'가 들어간 제목 아래의 목록 항목만 뽑는다.

    같은 깊이 이하의 다음 제목을 만나면 멈춘다. 표(`|...|`)는 읽지 않는다 —
    형식이 굳기 전에는 목록만 본다.
    """
    lines = text.splitlines()
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

    if not found_section:
        raise ScanLogError(
            "로그에서 '후보' 섹션을 찾지 못했습니다.\n"
            "  `## 후보` 같은 제목 아래에 목록으로 적어주세요:\n"
            '    ## 후보\n    - 소재 한 줄\n    - 소재 한 줄\n'
            '  또는 후보를 인자로 직접 넘기세요.')
    if not items:
        raise ScanLogError(
            "'후보' 섹션은 찾았지만 목록 항목이 없습니다.\n"
            '  `- ` 로 시작하는 줄로 적어주세요. 표는 읽지 않습니다.')
    return items


def _clean(text):
    """마크다운 강조·링크 껍데기만 벗긴다. 내용은 그대로 둔다."""
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)    # [텍스트](링크)
    text = re.sub(r'[*_`]{1,3}', '', text)
    return text.strip()


def read_candidates(log_dir, date_str):
    path = log_path(log_dir, date_str)
    with open(path, encoding='utf-8') as fh:
        return parse_candidates(fh.read()), path
