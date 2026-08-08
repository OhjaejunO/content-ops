from django.contrib import admin

from .models import Deadline, Episode, Source


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'category', 'status', 'published_at', 'created_at')


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'url', 'collected_at', 'episode')


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = ('title', 'due_date', 'd_day_label', 'official_url', 'episode')

    @admin.display(description='D-day', ordering='due_date')
    def d_day_label(self, obj):
        return obj.d_day_label
