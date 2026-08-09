from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Episode(models.Model):
    """발행 단위 콘텐츠 1건."""

    class Category(models.TextChoices):
        AI_NEWS = 'ai_news', 'AI소식'
        HANDS_ON = 'hands_on', '두드려봄'
        OPPORTUNITY = 'opportunity', '기회'
        TIP = 'tip', '꿀팁'

    class Status(models.TextChoices):
        PRODUCING = 'producing', '제작중'
        PRODUCED = 'produced', '제작완료'
        PUBLISHED = 'published', '발행완료'
        CANCELED = 'canceled', '발행취소'

    #: 각 상태에서 넘어갈 수 있는 다음 상태. 여기 없는 조합은 전부 막는다.
    #: 발행완료와 발행취소는 종착 상태이므로 빠져나가는 길이 없다.
    ALLOWED_TRANSITIONS = {
        Status.PRODUCING: {Status.PRODUCED},
        Status.PRODUCED: {Status.PUBLISHED, Status.CANCELED},
        Status.PUBLISHED: set(),
        Status.CANCELED: set(),
    }

    number = models.PositiveIntegerField('번호', unique=True)
    title = models.CharField('제목', max_length=200)
    category = models.CharField('카테고리', max_length=20, choices=Category.choices)
    status = models.CharField(
        '상태', max_length=20, choices=Status.choices, default=Status.PRODUCING
    )
    published_at = models.DateTimeField('발행일', null=True, blank=True)
    cancel_reason = models.TextField('취소사유', null=True, blank=True)
    created_at = models.DateTimeField('생성일시', auto_now_add=True)

    def stored_status(self):
        """DB에 저장돼 있는 현재 상태. 아직 저장 전이면 None."""
        if self._state.adding:
            return None
        return (
            type(self)
            ._base_manager.filter(pk=self.pk)
            .values_list('status', flat=True)
            .first()
        )

    def validate_status_transition(self):
        """상태 전이 규칙 위반이면 ValidationError를 던진다.

        검사는 '상태가 바뀔 때'만 한다. 이미 그 상태로 저장돼 있는 건을
        다시 저장하는 것(제목 수정 등)은 전이가 아니므로 통과시킨다.
        발행일이 확인되지 않은 채 넘어온 과거 데이터를 손댈 수 없게 되는 것을
        막기 위해서다.
        """
        previous = self.stored_status()
        if previous == self.status:
            return

        errors = {}

        if previous is not None and self.status not in self.ALLOWED_TRANSITIONS[previous]:
            errors['status'] = ValidationError(
                '%(before)s → %(after)s 전이는 허용되지 않습니다.',
                code='invalid_transition',
                params={
                    'before': self.Status(previous).label,
                    'after': self.Status(self.status).label,
                },
            )

        if self.status == self.Status.PUBLISHED and self.published_at is None:
            errors['published_at'] = ValidationError(
                '발행완료로 바꾸려면 발행일이 있어야 합니다.', code='published_at_required'
            )

        if self.status == self.Status.CANCELED and not (self.cancel_reason or '').strip():
            errors['cancel_reason'] = ValidationError(
                '발행취소로 바꾸려면 취소사유가 있어야 합니다.', code='cancel_reason_required'
            )

        if errors:
            raise ValidationError(errors)

    def clean(self):
        super().clean()
        self.validate_status_transition()

    def save(self, *args, **kwargs):
        # admin 폼을 타지 않는 경로(shell, 스크립트)에서도 규칙이 걸리도록
        # clean()에만 두지 않고 save()에서도 검사한다.
        self.validate_status_transition()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'ep{self.number} {self.title}'


class Topic(models.Model):
    """에피소드가 다루는 사건/주제 1건.

    노출 횟수를 세는 단위가 소재(Source)가 아니라 사건인 이유는, 서로 다른
    URL 여러 개가 같은 사건을 다루는 경우가 실제로 중복 노출 사고의 형태였기
    때문이다. URL 단위로 세면 그 경우가 통과한다.
    """

    name = models.CharField('사건/주제', max_length=200, unique=True)
    created_at = models.DateTimeField('생성일시', auto_now_add=True)
    # 중복 감지용 임베딩 캐시. Topic 수십 개 규모라 벡터DB를 둘 이유가 없고,
    # 매번 다시 인코딩하는 것이 유일한 비용이므로 그것만 없앤다.
    embedding = models.BinaryField('임베딩 캐시', null=True, blank=True, editable=False)
    embedding_key = models.CharField(
        '임베딩 캐시 키', max_length=64, blank=True, default='', editable=False
    )
    episodes = models.ManyToManyField(
        Episode,
        verbose_name='연결 에피소드',
        blank=True,
        related_name='topics',
    )

    @property
    def exposure_count(self):
        """이 사건이 실제로 노출된 횟수.

        발행완료만 센다. 제작만 해둔 건과 발행을 접은 건은 밖으로 나가지
        않았으므로 노출이 아니다. 중복 노출 판단의 기준은 '만들었는가'가
        아니라 '내보냈는가'다.
        """
        return self.episodes.filter(status=Episode.Status.PUBLISHED).count()

    def __str__(self):
        return self.name


class Source(models.Model):
    """에피소드의 근거가 되는 원본 자료."""

    url = models.URLField('원본 URL', max_length=500)
    collected_at = models.DateTimeField('수집일시')
    summary = models.TextField('요약', blank=True)
    episode = models.ForeignKey(
        Episode,
        verbose_name='연결 에피소드',
        # SET_NULL이면 에피소드를 지울 때 근거가 조용히 끊기고, 그 소재를
        # 다뤘다는 이력이 사라진다. 노출 이력이 사라지는 경로를 막는 것이
        # 이 모델의 목적이므로 삭제를 막는 쪽을 택한다.
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sources',
    )


class DeadlineQuerySet(models.QuerySet):
    def active(self):
        """아직 마감되지 않은 건만, 급한 순서대로."""
        return self.filter(due_date__gte=timezone.localdate()).order_by('due_date')


class Deadline(models.Model):
    """마감이 있는 기회(공모/지원/신청) 정보."""

    title = models.CharField('제목', max_length=200)
    due_date = models.DateField('마감일')
    official_url = models.URLField('공식링크', max_length=500)
    episode = models.ForeignKey(
        Episode,
        verbose_name='연결 에피소드',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deadlines',
    )

    objects = DeadlineQuerySet.as_manager()

    @property
    def days_left(self):
        """오늘 기준 남은 일수. 마감 당일은 0, 지났으면 음수.

        기준일은 settings.TIME_ZONE(Asia/Seoul)의 '오늘'이다. UTC로 계산하면
        한국 시간 자정~오전 9시 사이에 하루가 어긋난다.
        """
        return (self.due_date - timezone.localdate()).days

    @property
    def is_expired(self):
        """마감일이 지났는지. 마감 당일은 아직 지나지 않은 것으로 본다."""
        return self.days_left < 0

    @property
    def d_day_label(self):
        """'D-18' / 'D-DAY' / '마감' 형식의 표시용 문자열."""
        days_left = self.days_left
        if days_left > 0:
            return f'D-{days_left}'
        if days_left == 0:
            return 'D-DAY'
        return '마감'
