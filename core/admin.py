from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from core.models import OfficerProfile, Report, ReportEvidence, SiteNotice


class EvidenceInline(admin.TabularInline):
    model = ReportEvidence
    extra = 0
    readonly_fields = ("kind", "file", "caption", "is_resolution", "created_at")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("public_id", "title", "category", "status", "claimed_by", "created_at")
    list_filter = ("status", "category", "created_at")
    search_fields = ("public_id", "title", "description", "location_text")
    readonly_fields = ("public_id", "view_count", "created_at", "updated_at")
    inlines = [EvidenceInline]
    actions = ["release_claims"]

    @admin.action(description="Release selected claims back to Awaiting Justice")
    def release_claims(self, request, queryset):
        n = queryset.filter(status=Report.Status.INVESTIGATING).update(
            status=Report.Status.PENDING, claimed_by=None, claimed_at=None
        )
        self.message_user(request, f"Released {n} claim(s).")


class OfficerProfileInline(admin.StackedInline):
    model = OfficerProfile
    can_delete = False


class UserAdmin(BaseUserAdmin):
    inlines = [OfficerProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(SiteNotice)
class SiteNoticeAdmin(admin.ModelAdmin):
    list_display = ("message", "level", "is_active", "order", "starts_at", "ends_at", "updated_at")
    list_filter = ("level", "is_active")
    search_fields = ("key", "message")
    list_editable = ("is_active", "order")
    actions = ["activate", "deactivate"]

    @admin.action(description="Take selected notices live")
    def activate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} notice(s) now live.")

    @admin.action(description="Pull selected notices down")
    def deactivate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} notice(s) pulled down.")
