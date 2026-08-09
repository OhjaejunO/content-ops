"""아침 스캔 후보 여러 건을 한 번에 대조한다.

    python manage.py scan_check "후보1" "후보2" "후보3"
    python manage.py scan_check < 후보목록.txt        # 한 줄에 하나

`check_topic` 이 한 건을 깊게 본다면 이것은 여러 건을 넓게 훑는다. 아침 스캔에서
후보가 2~3개씩 나오는데(SKILL §5.5) 하나씩 돌리면 Topic 임베딩을 매번 다시
읽어야 하고, 무엇보다 후보끼리 비교가 안 된다.

**이 명령도 아무것도 바꾸지 않는다.** 참고 라벨을 붙일 뿐 승격은 사람이 한다.
"""
import sys

from django.core.management.base import BaseCommand, CommandError

from ... import similarity
from . import _topic_common as common

COL_CAND = 34
COL_TOPIC = 22


class Command(BaseCommand):
    help = '소재 후보 여러 건을 기존 Topic과 대조해 참고 라벨을 붙입니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            'candidates', nargs='*',
            help='소재 후보. 생략하면 stdin에서 한 줄에 하나씩 읽습니다',
        )
        parser.add_argument(
            '--refresh', action='store_true',
            help='캐시된 임베딩을 무시하고 다시 계산합니다',
        )

    def handle(self, *args, **options):
        candidates = [c.strip() for c in options['candidates'] if c.strip()]
        if not candidates and not sys.stdin.isatty():
            candidates = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
        if not candidates:
            raise CommandError(
                '후보가 비어 있습니다. 인자로 넘기거나 stdin으로 한 줄에 하나씩 주세요.')

        topics = common.load_topics(self.stdout)
        if topics is None:
            return

        results = common.rank(candidates, topics, top_n=3,
                              refresh=options['refresh'])

        self.stdout.write(f'후보 {len(candidates)}건')
        self.stdout.write('')
        self.stdout.write(
            common.fit('후보', COL_CAND) + common.fit('1위 Topic', COL_TOPIC)
            + '유사도  노출  참고')
        self.stdout.write('─' * 96)

        for text, ranked in zip(candidates, results):
            if not ranked:
                self.stdout.write(common.fit(text, COL_CAND) + '비교 대상 없음')
                continue
            top = ranked[0]
            self.stdout.write(
                common.fit(text, COL_CAND)
                + common.fit(top['topic'].name, COL_TOPIC)
                + f'{top["score"]:>6.3f}'
                + f'{top["topic"].exposure_count:>5}회  '
                + similarity.advice(ranked)
            )

        self.stdout.write('')
        self.stdout.write(common.ADVISORY)
