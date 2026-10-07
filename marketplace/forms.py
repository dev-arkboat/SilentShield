from django import forms

from marketplace.models import ContactRequest


class ContactRequestForm(forms.ModelForm):
    class Meta:
        model = ContactRequest
        fields = ["subject", "message", "callback"]
        widgets = {
            "subject": forms.TextInput(attrs={"maxlength": 140, "autocomplete": "off"}),
            "message": forms.Textarea(attrs={"rows": 5, "maxlength": 2000}),
            "callback": forms.TextInput(
                attrs={"maxlength": 140, "autocomplete": "off", "placeholder": "optional throwaway relay"}
            ),
        }
        help_texts = {
            "message": "Describe the help you need. Do NOT include your real name, phone or email.",
        }
