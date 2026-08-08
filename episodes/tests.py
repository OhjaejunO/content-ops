from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import Episode


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
