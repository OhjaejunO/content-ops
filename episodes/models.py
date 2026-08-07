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

    number = models.PositiveIntegerField('번호', unique=True)
    title = models.CharField('제목', max_length=200)
    category = models.CharField('카테고리', max_length=20, choices=Category.choices)
    status = models.CharField(
        '상태', max_length=20, choices=Status.choices, default=Status.PRODUCING
    )
    published_at = models.DateTimeField('발행일', null=True, blank=True)
    cancel_reason = models.TextField('취소사유', null=True, blank=True)
    created_at = models.DateTimeField('생성일시', auto_now_add=True)


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
