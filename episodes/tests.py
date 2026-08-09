import datetime
from contextlib import contextmanager
from unittest import mock

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from .models import Deadline, Episode, Source, Topic

SEOUL = datetime.timezone(datetime.timedelta(hours=9))


@contextmanager
def frozen_now(*args):
    """timezone.now()를 고정한다. 인자는 UTC 기준 datetime 구성요소.

    localdate()는 고정된 now()를 실제 Asia/Seoul 규칙으로 변환하므로,
    타임존 변환 자체는 가짜로 만들지 않고 그대로 검증된다.
    """
    fixed = datetime.datetime(*args, tzinfo=datetime.timezone.utc)
    with mock.patch.object(timezone, 'now', return_value=fixed):
        yield fixed


def make_episode(number=1, **kwargs):
    """제작중 상태의 에피소드 1건을 만들어 반환한다."""
    fields = {
        'number': number,
        'title': f'테스트 에피소드 {number}',
        'category': Episode.Category.AI_NEWS,
        'status': Episode.Status.PRODUCING,
    }
    fields.update(kwargs)
    return Episode.objects.create(**fields)


class ForwardTransitionTests(TestCase):
    """순방향 전이는 통과해야 한다."""

    def test_producing_to_produced(self):
        episode = make_episode()

        episode.status = Episode.Status.PRODUCED
        episode.save()

        episode.refresh_from_db()
        self.assertEqual(episode.status, Episode.Status.PRODUCED)

    def test_produced_to_published_with_published_at(self):
        episode = make_episode(status=Episode.Status.PRODUCED)

        episode.status = Episode.Status.PUBLISHED
        episode.published_at = timezone.now()
        episode.save()

        episode.refresh_from_db()
        self.assertEqual(episode.status, Episode.Status.PUBLISHED)

    def test_produced_to_canceled_with_reason(self):
        episode = make_episode(status=Episode.Status.PRODUCED)

        episode.status = Episode.Status.CANCELED
        episode.cancel_reason = '동일 사건 3회 노출 회피'
        episode.save()

        episode.refresh_from_db()
        self.assertEqual(episode.status, Episode.Status.CANCELED)

    def test_full_path_producing_to_published(self):
        episode = make_episode()

        episode.status = Episode.Status.PRODUCED
        episode.save()
        episode.status = Episode.Status.PUBLISHED
        episode.published_at = timezone.now()
        episode.save()

        episode.refresh_from_db()
        self.assertEqual(episode.status, Episode.Status.PUBLISHED)

    def test_saving_without_changing_status_is_not_a_transition(self):
        """발행일이 비어 있는 과거 발행완료 건도 수정은 가능해야 한다."""
        # loaddata가 그렇듯 save()를 타지 않고 들어온 과거 데이터를 재현한다.
        episode = make_episode()
        Episode.objects.filter(pk=episode.pk).update(
            status=Episode.Status.PUBLISHED, published_at=None
        )
        episode.refresh_from_db()

        episode.title = '제목만 고침'
        episode.save()

        episode.refresh_from_db()
        self.assertEqual(episode.title, '제목만 고침')


class BackwardTransitionTests(TestCase):
    """역행 전이는 막혀야 한다."""

    def test_produced_to_producing_is_rejected(self):
        episode = make_episode(status=Episode.Status.PRODUCED)

        episode.status = Episode.Status.PRODUCING
        with self.assertRaises(ValidationError) as ctx:
            episode.save()

        self.assertIn('status', ctx.exception.error_dict)

    def test_published_to_produced_is_rejected(self):
        episode = make_episode(
            status=Episode.Status.PUBLISHED, published_at=timezone.now()
        )

        episode.status = Episode.Status.PRODUCED
        with self.assertRaises(ValidationError):
            episode.save()

    def test_producing_to_published_skips_a_step_and_is_rejected(self):
        episode = make_episode()

        episode.status = Episode.Status.PUBLISHED
        episode.published_at = timezone.now()
        with self.assertRaises(ValidationError):
            episode.save()

    def test_rejected_transition_is_not_persisted(self):
        episode = make_episode(status=Episode.Status.PRODUCED)

        episode.status = Episode.Status.PRODUCING
        with self.assertRaises(ValidationError):
            episode.save()

        self.assertEqual(
            Episode.objects.get(pk=episode.pk).status, Episode.Status.PRODUCED
        )


class CancelTransitionTests(TestCase):
    """발행취소는 제작완료에서만 가능하다."""

    def test_published_to_canceled_is_rejected(self):
        episode = make_episode(
            status=Episode.Status.PUBLISHED, published_at=timezone.now()
        )

        episode.status = Episode.Status.CANCELED
        episode.cancel_reason = '내려야 할 사유가 생김'
        with self.assertRaises(ValidationError) as ctx:
            episode.save()

        self.assertIn('status', ctx.exception.error_dict)

    def test_producing_to_canceled_is_rejected(self):
        episode = make_episode()

        episode.status = Episode.Status.CANCELED
        episode.cancel_reason = '접기로 함'
        with self.assertRaises(ValidationError):
            episode.save()


class RequiredFieldTests(TestCase):
    """전이에 필요한 근거 필드가 없으면 막힌다."""

    def test_published_without_published_at_is_rejected(self):
        episode = make_episode(status=Episode.Status.PRODUCED)

        episode.status = Episode.Status.PUBLISHED
        with self.assertRaises(ValidationError) as ctx:
            episode.save()

        self.assertIn('published_at', ctx.exception.error_dict)

    def test_canceled_without_reason_is_rejected(self):
        episode = make_episode(status=Episode.Status.PRODUCED)

        episode.status = Episode.Status.CANCELED
        with self.assertRaises(ValidationError) as ctx:
            episode.save()

        self.assertIn('cancel_reason', ctx.exception.error_dict)

    def test_canceled_with_blank_reason_is_rejected(self):
        episode = make_episode(status=Episode.Status.PRODUCED)

        episode.status = Episode.Status.CANCELED
        episode.cancel_reason = '   '
        with self.assertRaises(ValidationError) as ctx:
            episode.save()

        self.assertIn('cancel_reason', ctx.exception.error_dict)


class CleanTests(TestCase):
    """admin 폼 경로(clean)에서도 같은 규칙이 걸린다."""

    def test_clean_rejects_backward_transition(self):
        episode = make_episode(status=Episode.Status.PRODUCED)

        episode.status = Episode.Status.PRODUCING
        with self.assertRaises(ValidationError):
            episode.full_clean()

    def test_clean_passes_for_valid_transition(self):
        episode = make_episode(status=Episode.Status.PRODUCED)

        episode.status = Episode.Status.PUBLISHED
        episode.published_at = timezone.now()
        episode.full_clean()  # 예외가 나지 않아야 한다


def make_deadline(due_date, title='테스트 마감', **kwargs):
    return Deadline.objects.create(
        title=title,
        due_date=due_date,
        official_url=kwargs.pop('official_url', 'https://example.com/'),
        **kwargs,
    )


class DaysLeftTests(TestCase):
    """오늘 날짜에 의존하지 않도록 now()를 고정하고 검증한다."""

    def test_future_deadline(self):
        deadline = make_deadline(datetime.date(2026, 8, 26))

        with frozen_now(2026, 8, 8, 3, 0):  # KST 8/8 12:00
            self.assertEqual(deadline.days_left, 18)
            self.assertFalse(deadline.is_expired)
            self.assertEqual(deadline.d_day_label, 'D-18')

    def test_due_today(self):
        deadline = make_deadline(datetime.date(2026, 8, 8))

        with frozen_now(2026, 8, 8, 3, 0):
            self.assertEqual(deadline.days_left, 0)
            self.assertFalse(deadline.is_expired)
            self.assertEqual(deadline.d_day_label, 'D-DAY')

    def test_past_deadline(self):
        deadline = make_deadline(datetime.date(2026, 8, 1))

        with frozen_now(2026, 8, 8, 3, 0):
            self.assertEqual(deadline.days_left, -7)
            self.assertTrue(deadline.is_expired)
            self.assertEqual(deadline.d_day_label, '마감')

    def test_tomorrow_is_d_minus_1(self):
        deadline = make_deadline(datetime.date(2026, 8, 9))

        with frozen_now(2026, 8, 8, 3, 0):
            self.assertEqual(deadline.d_day_label, 'D-1')

    def test_yesterday_is_expired(self):
        deadline = make_deadline(datetime.date(2026, 8, 7))

        with frozen_now(2026, 8, 8, 3, 0):
            self.assertEqual(deadline.days_left, -1)
            self.assertTrue(deadline.is_expired)


class TimezoneBoundaryTests(TestCase):
    """UTC로 계산하면 어긋나는 구간을 짚는다."""

    def test_just_before_seoul_midnight(self):
        """KST 8/8 23:59 = UTC 8/8 14:59. 서울 기준 오늘은 8/8."""
        deadline = make_deadline(datetime.date(2026, 8, 8))

        with frozen_now(2026, 8, 8, 14, 59) as now:
            self.assertEqual(now.astimezone(SEOUL).date(), datetime.date(2026, 8, 8))
            self.assertEqual(deadline.days_left, 0)
            self.assertEqual(deadline.d_day_label, 'D-DAY')

    def test_just_after_seoul_midnight(self):
        """KST 8/9 00:01 = UTC 8/8 15:01. UTC로는 아직 8/8이지만 서울은 8/9."""
        deadline = make_deadline(datetime.date(2026, 8, 8))

        with frozen_now(2026, 8, 8, 15, 1) as now:
            self.assertEqual(now.date(), datetime.date(2026, 8, 8))
            self.assertEqual(now.astimezone(SEOUL).date(), datetime.date(2026, 8, 9))
            self.assertEqual(deadline.days_left, -1)
            self.assertTrue(deadline.is_expired)
            self.assertEqual(deadline.d_day_label, '마감')

    def test_early_seoul_morning_is_already_the_new_day(self):
        """KST 8/8 08:00 = UTC 8/7 23:00. UTC로는 어제라 하루가 어긋난다."""
        deadline = make_deadline(datetime.date(2026, 8, 8))

        with frozen_now(2026, 8, 7, 23, 0) as now:
            self.assertEqual(now.date(), datetime.date(2026, 8, 7))
            self.assertEqual(deadline.d_day_label, 'D-DAY')


class ActiveQuerySetTests(TestCase):
    def test_excludes_expired_and_sorts_by_due_date(self):
        make_deadline(datetime.date(2026, 9, 1), title='늦은 마감')
        make_deadline(datetime.date(2026, 8, 26), title='이른 마감')
        make_deadline(datetime.date(2026, 8, 8), title='오늘 마감')
        make_deadline(datetime.date(2026, 8, 7), title='지난 마감')

        with frozen_now(2026, 8, 8, 3, 0):
            titles = list(Deadline.objects.active().values_list('title', flat=True))

        self.assertEqual(titles, ['오늘 마감', '이른 마감', '늦은 마감'])

    def test_due_today_is_still_active(self):
        make_deadline(datetime.date(2026, 8, 8), title='오늘 마감')

        with frozen_now(2026, 8, 8, 14, 59):
            self.assertEqual(Deadline.objects.active().count(), 1)

    def test_due_today_drops_out_after_seoul_midnight(self):
        make_deadline(datetime.date(2026, 8, 8), title='오늘 마감')

        with frozen_now(2026, 8, 8, 15, 1):
            self.assertEqual(Deadline.objects.active().count(), 0)

    def test_empty_when_everything_expired(self):
        make_deadline(datetime.date(2026, 8, 1))

        with frozen_now(2026, 8, 8, 3, 0):
            self.assertFalse(Deadline.objects.active().exists())


class SeedDeadlineTests(TestCase):
    """시드된 마감 2건이 실제로 어떻게 보이는지 확인한다."""

    fixtures = ['initial_episodes.json']

    def test_seeded_deadlines_on_seed_date(self):
        with frozen_now(2026, 8, 8, 3, 0):
            labels = {d.title: d.d_day_label for d in Deadline.objects.active()}

        self.assertEqual(labels['OpenAI 서울 해커톤 접수 마감'], 'D-18')
        self.assertEqual(labels['Higgsfield 영화제 마감'], 'D-24')


class ExposureCountTests(TestCase):
    """노출 횟수는 '내보낸 것'만 센다."""

    def setUp(self):
        self.topic = Topic.objects.create(name='AI 평가장 사고')

    def test_counts_published_episodes(self):
        self.topic.episodes.add(
            make_episode(1, status=Episode.Status.PUBLISHED, published_at=timezone.now()),
            make_episode(2, status=Episode.Status.PUBLISHED, published_at=timezone.now()),
        )

        self.assertEqual(self.topic.exposure_count, 2)

    def test_canceled_episode_is_not_an_exposure(self):
        self.topic.episodes.add(
            make_episode(1, status=Episode.Status.PUBLISHED, published_at=timezone.now()),
            make_episode(2, status=Episode.Status.CANCELED, cancel_reason='접음'),
        )

        self.assertEqual(self.topic.exposure_count, 1)

    def test_unpublished_episodes_are_not_exposures(self):
        self.topic.episodes.add(
            make_episode(1, status=Episode.Status.PRODUCING),
            make_episode(2, status=Episode.Status.PRODUCED),
            make_episode(3, status=Episode.Status.CANCELED, cancel_reason='접음'),
        )

        self.assertEqual(self.topic.exposure_count, 0)

    def test_empty_topic_counts_zero(self):
        self.assertEqual(self.topic.exposure_count, 0)

    def test_cancellation_does_not_decrement_past_exposures(self):
        """이미 발행된 건이 있으면 다른 건을 접어도 노출 이력은 남는다."""
        published = make_episode(
            1, status=Episode.Status.PUBLISHED, published_at=timezone.now()
        )
        canceled = make_episode(2, status=Episode.Status.PRODUCED)
        self.topic.episodes.add(published, canceled)

        canceled.status = Episode.Status.CANCELED
        canceled.cancel_reason = '동일 사건 중복'
        canceled.save()

        self.assertEqual(self.topic.exposure_count, 1)


class TopicRelationTests(TestCase):
    def test_relation_is_bidirectional(self):
        topic = Topic.objects.create(name='AI 평가장 사고')
        episode = make_episode(1)
        topic.episodes.add(episode)

        self.assertIn(episode, topic.episodes.all())
        self.assertIn(topic, episode.topics.all())

    def test_episode_can_carry_several_topics(self):
        episode = make_episode(1)
        first = Topic.objects.create(name='AI 평가장 사고')
        second = Topic.objects.create(name='Qwen3.8-Max 출시')
        episode.topics.add(first, second)

        self.assertEqual(episode.topics.count(), 2)

    def test_topic_can_carry_several_episodes(self):
        topic = Topic.objects.create(name='AI 평가장 사고')
        topic.episodes.add(make_episode(1), make_episode(2))

        self.assertEqual(topic.episodes.count(), 2)

    def test_name_is_unique(self):
        Topic.objects.create(name='AI 평가장 사고')

        with self.assertRaises(ValidationError):
            Topic(name='AI 평가장 사고').full_clean()


class SourceProtectTests(TestCase):
    """에피소드를 지워도 근거가 조용히 끊기지 않아야 한다."""

    def test_deleting_an_episode_with_sources_is_blocked(self):
        episode = make_episode(1)
        Source.objects.create(
            url='https://example.com/article',
            collected_at=timezone.now(),
            episode=episode,
        )

        with self.assertRaises(ProtectedError):
            episode.delete()

        self.assertTrue(Episode.objects.filter(pk=episode.pk).exists())
        self.assertEqual(Source.objects.count(), 1)

    def test_episode_without_sources_can_be_deleted(self):
        episode = make_episode(1)

        episode.delete()

        self.assertFalse(Episode.objects.filter(pk=episode.pk).exists())


class SeedTopicTests(TestCase):
    """ep8 취소 사유를 데이터로 복원할 수 있는지 확인한다."""

    fixtures = ['initial_episodes.json']

    def test_seeded_topics_exist(self):
        self.assertEqual(Topic.objects.count(), 2)

    def test_accident_topic_counts_only_the_published_episode(self):
        topic = Topic.objects.get(name='AI 평가장 사고')

        self.assertEqual(topic.exposure_count, 1)
        self.assertEqual(
            set(topic.episodes.values_list('number', flat=True)), {6, 8}
        )

    def test_canceled_episode_stays_linked_to_its_topic(self):
        """ep8이 무엇을 다루려다 접혔는지가 조회로 답해져야 한다."""
        ep8 = Episode.objects.get(number=8)

        topic = ep8.topics.get()

        self.assertEqual(topic.name, 'AI 평가장 사고')
        self.assertEqual(ep8.status, Episode.Status.CANCELED)

    def test_already_published_episodes_for_ep8_topic_are_queryable(self):
        ep8 = Episode.objects.get(number=8)
        topic = ep8.topics.get()

        already_out = topic.episodes.filter(
            status=Episode.Status.PUBLISHED
        ).exclude(pk=ep8.pk)

        self.assertEqual(list(already_out.values_list('number', flat=True)), [6])

    def test_qwen_topic_has_one_exposure(self):
        topic = Topic.objects.get(name='Qwen3.8-Max 출시')

        self.assertEqual(topic.exposure_count, 1)


class SeedFixtureTests(TestCase):
    """시드 fixture가 전이 규칙과 무관하게 그대로 적재되는지 확인한다."""

    fixtures = ['initial_episodes.json']

    def test_fixture_loads_all_records(self):
        self.assertEqual(Episode.objects.count(), 10)

    def test_canceled_episode_kept_its_reason(self):
        episode = Episode.objects.get(number=8)
        self.assertEqual(episode.status, Episode.Status.CANCELED)
        self.assertTrue(episode.cancel_reason)

    def test_unconfirmed_publish_dates_stay_null(self):
        unconfirmed = Episode.objects.filter(number__in=[1, 2, 3, 4, 5])
        self.assertEqual(unconfirmed.filter(published_at__isnull=True).count(), 5)
