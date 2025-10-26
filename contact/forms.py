from django import forms


class ContactForm(forms.Form):
    subject = forms.CharField(max_length=255, required=False)
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 6, 'autocomplete': 'off'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Subject can be autocompleted in some browsers; message body is free text
        self.fields['subject'].widget.attrs.update({'autocomplete': 'on'})
