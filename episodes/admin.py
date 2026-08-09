from django.contrib import admin
from django.utils.html import format_html

from .models import Deadline, Episode, Source, Topic


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'category', 'status', 'published_at', 'created_at')


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'exposure_count', 'created_at')
    filter_horizontal = ('episodes',)

    @admin.display(description='노출 횟수')
    def exposure_count(self, obj):
        return obj.exposure_count


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'url', 'collected_at', 'episode')


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    """만료된 마감은 목록에서 **구분만 하고 지우지 않는다.**

    `active()` 가 이미 걸러내므로 실무 조회에는 안 걸리지만, 행 자체는 남긴다.
    지난 기회를 언제 다뤘는지가 남아야 다음에 같은 공모가 열렸을 때 근거가 된다
    — 이력이 조용히 사라지는 경로를 막는다는 점에서 `Source` 의 PROTECT 와 같은 취지다.
    """

    list_display = ('title', 'due_date', 'd_day_label', 'expiry', 'official_url', 'episode')
    list_filter = ('due_date',)

    @admin.display(description='D-day', ordering='due_date')
    def d_day_label(self, obj):
        return obj.d_day_label

    @admin.display(description='상태')
    def expiry(self, obj):
        if obj.is_expired:
            return format_html(
                '<span style="background:#F3E4E0;color:#A4462B;border-radius:9px;'
                'padding:2px 9px;font-weight:700">만료</span>')
        return format_html(
            '<span style="background:#E6F9FB;color:#17808C;border-radius:9px;'
            'padding:2px 9px;font-weight:700">진행</span>')
