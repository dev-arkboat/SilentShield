from django.contrib import admin

from marketplace.models import ContactRequest, HackerProfile, HackerRating


class RatingInline(admin.TabularInline):
    model = HackerRating
    extra = 0


@admin.register(HackerProfile)
class HackerProfileAdmin(admin.ModelAdmin):
    list_display = ("nickname", "rating", "ratings_count", "is_verified", "is_listed", "affiliated_org")
    list_filter = ("is_verified", "is_listed")
    search_fields = ("nickname", "skills", "services")
    inlines = [RatingInline]

    def get_fields(self, request, obj=None):
        fields = ["nickname", "tagline", "bio", "skills", "services", "price_range",
                  "avatar", "relay_handle", "affiliated_org", "rating", "ratings_count",
                  "is_verified", "is_listed", "verified_by", "verified_at"]
        # Real identity dossier: superusers only, never in public templates.
        if request.user.is_superuser:
            fields.append("private_identity_ref")
        return fields


@admin.register(HackerRating)
class HackerRatingAdmin(admin.ModelAdmin):
    list_display = ("hacker", "score", "created_by", "created_at")
    list_filter = ("score",)


@admin.register(ContactRequest)
class ContactRequestAdmin(admin.ModelAdmin):
    list_display = ("hacker", "subject", "status", "created_at")
    list_filter = ("status", "created_at")
