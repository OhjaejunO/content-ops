"""check_topic · scan_check 가 함께 쓰는 부분.

두 명령이 같은 판정을 하는데 코드가 갈리면 둘의 결과가 조용히 달라진다.
비교 대상을 고르는 것, 의존성 부재를 안내로 바꾸는 것, 그리고 마지막에
"결정하지 않는다"고 못박는 문구는 한 곳에만 둔다.

이름이 `_` 로 시작해 Django 명령 탐색에서 제외된다 — 명령이 아니라 공용 모듈이다.
"""
import unicodedata

from django.core.management.base import CommandError

from ... import similarity
from ...models import Topic

#: README 원칙. 두 명령 모두 출력 마지막에 이 문장을 붙인다.
ADVISORY = '판정은 참고용입니다. 승격은 사람이 결정합니다.'


def load_topics(stdout):
    """비교 대상 Topic. 없으면 안내만 찍고 None."""
    topics = Topic.objects.prefetch_related('episodes')
    if not topics.exists():
        stdout.write('등록된 Topic이 없습니다. 비교할 대상이 없습니다.')
        return None
    return topics


def rank(queries, topics, top_n=3, refresh=False):
    """임베딩 의존성이 없으면 트레이스백 대신 설치 안내로 끝낸다."""
    try:
        return similarity.rank_many(queries, topics, top_n=top_n, refresh=refresh)
    except similarity.EmbeddingUnavailable as exc:
        raise CommandError(str(exc)) from exc


def width(text):
    """터미널 표시 폭. 한글·전각은 두 칸을 차지한다."""
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in text)


def fit(text, cells):
    """표 한 칸에 맞춰 자르고 남는 만큼 공백을 채운다."""
    out = ''
    used = 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in 'WF' else 1
        if used + w > cells - 1:
            out += '…'
            used += 1
            break
        out += ch
        used += w
    return out + ' ' * max(0, cells - used)
