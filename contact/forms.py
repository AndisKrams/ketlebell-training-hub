from django import forms


class ContactForm(forms.Form):
    subject = forms.CharField(max_length=255, required=False)
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 6}))
