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
    list_display = ('title', 'due_date', 'official_url', 'episode')
