from django.core.exceptions import ValidationError
from django.db import models


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


class Source(models.Model):
    """에피소드의 근거가 되는 원본 자료."""

    url = models.URLField('원본 URL', max_length=500)
    collected_at = models.DateTimeField('수집일시')
    summary = models.TextField('요약', blank=True)
    episode = models.ForeignKey(
        Episode,
        verbose_name='연결 에피소드',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sources',
    )


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
