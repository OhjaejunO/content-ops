"""새 소재가 기존 사건과 겹치는지 후보를 제시한다.

    python manage.py check_topic "제목 또는 요약문"

판정이지 결정이 아니다. 이 명령은 아무것도 바꾸지 않고 출력만 한다.
"""

from django.core.management.base import BaseCommand, CommandError

from ...models import Episode
from . import _topic_common as common


class Command(BaseCommand):
    help = '새 소재가 기존 Topic 중 어느 것과 겹치는지 유사도로 후보를 제시합니다.'

    def add_arguments(self, parser):
        parser.add_argument('text', help='판정할 제목 또는 요약문')
        parser.add_argument(
            '--top', type=int, default=3, help='출력할 후보 수 (기본 3)'
        )
        parser.add_argument(
            '--refresh',
            action='store_true',
            help='캐시된 임베딩을 무시하고 다시 계산합니다',
        )

    def handle(self, *args, **options):
        text = options['text'].strip()
        if not text:
            raise CommandError('판정할 텍스트가 비어 있습니다.')

        top_n = options['top']
        if top_n < 1:
            raise CommandError('--top은 1 이상이어야 합니다.')

        topics = common.load_topics(self.stdout)
        if topics is None:
            return

        ranked = common.rank(
            [text], topics, top_n=top_n, refresh=options['refresh']
        )[0]

        self.stdout.write(f'입력: {text}')
        self.stdout.write('')

        for rank, row in enumerate(ranked, start=1):
            topic = row['topic']
            self.stdout.write(
                f'{rank}. {topic.name}  '
                f'유사도 {row["score"]:.3f}  '
                f'노출 {topic.exposure_count}회'
            )
            for episode in topic.episodes.order_by('number'):
                marker = (
                    '노출'
                    if episode.status == Episode.Status.PUBLISHED
                    else episode.get_status_display()
                )
                self.stdout.write(
                    f'     ep{episode.number} {episode.title} [{marker}]'
                )
            self.stdout.write('')

        self.stdout.write(common.ADVISORY)
