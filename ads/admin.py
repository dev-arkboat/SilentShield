from django.contrib import admin

from ads.models import Ad, AdEvent, AdSlot


class AdInline(admin.TabularInline):
    model = Ad
    extra = 0
    readonly_fields = ("impressions", "clicks")


@admin.register(AdSlot)
class AdSlotAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "width", "height", "is_active")
    inlines = [AdInline]


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ("title", "sponsor", "slot", "is_active", "weight", "impressions", "clicks")
    list_filter = ("slot", "is_active")
    readonly_fields = ("impressions", "clicks")


@admin.register(AdEvent)
class AdEventAdmin(admin.ModelAdmin):
    list_display = ("ad", "kind", "created_at")
    list_filter = ("kind",)
