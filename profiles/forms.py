from django import forms
from collections import OrderedDict

from .models import UserProfile


class UserProfileForm(forms.ModelForm):
    # additional fields to edit the associated User
    full_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)

    class Meta:
        model = UserProfile
        # Do not expose the Stripe customer id in the profile form
        exclude = ("user", "stripe_customer_id")

    def __init__(self, *args, **kwargs):
        """Add placeholders and classes, remove auto-generated labels,
        and set autofocus on the first field.
        """
        super().__init__(*args, **kwargs)
        # Populate full_name and email initial values from the related User
        try:
            user = self.instance.user
            self.fields['full_name'].initial = user.get_full_name()
            self.fields['email'].initial = user.email
        except Exception:
            pass
        placeholders = {
            'default_phone_number': 'Phone Number',
            'default_postcode': 'Postal Code',
            'default_town_or_city': 'Town or City',
            'default_street_address1': 'Street Address 1',
            'default_street_address2': 'Street Address 2',
            'default_county': 'County, State or Locality',
            'full_name': 'Full name',
            'email': 'Email address',
        }

        # Set autofocus on full_name and placeholders, and unify classes
        if 'full_name' in self.fields:
            self.fields['full_name'].widget.attrs['autofocus'] = True

        cls = 'border-black rounded-0 profile-form-input'
        # Reorder fields so full_name and email appear above phone number
        desired = [
            'full_name',
            'email',
            'default_phone_number',
            'default_street_address1',
            'default_street_address2',
            'default_town_or_city',
            'default_county',
            'default_postcode',
            'default_country',
        ]
        # Preserve any other fields after the desired ordering
        ordered = OrderedDict()
        for name in desired:
            if name in self.fields:
                ordered[name] = self.fields.pop(name)
        for name, fld in list(self.fields.items()):
            ordered[name] = fld
        self.fields = ordered

        for field_name, field in self.fields.items():
            if field_name != 'default_country':
                base = placeholders.get(field_name, field.label)
                if field.required:
                    placeholder = base + ' '
                    placeholder += '*'
                else:
                    placeholder = base
                field.widget.attrs['placeholder'] = placeholder

            # Add semantic autocomplete attributes to help browser autofill
            autocomplete_map = {
                'full_name': 'name',
                'email': 'email',
                'default_phone_number': 'tel',
                'default_street_address1': 'address-line1',
                'default_street_address2': 'address-line2',
                'default_town_or_city': 'address-level2',
                'default_county': 'address-level1',
                'default_postcode': 'postal-code',
                'default_country': 'country',
            }
            ac = autocomplete_map.get(field_name)
            if ac:
                field.widget.attrs['autocomplete'] = ac

            field.widget.attrs['class'] = cls
            field.label = False

    def save(self, commit=True):
        """Save profile and update the related User's full name and email.
        """
        profile = super().save(commit=False)
        # Update user fields if provided
        try:
            user = profile.user
            full_name = self.cleaned_data.get('full_name')
            email = self.cleaned_data.get('email')
            if full_name:
                parts = full_name.strip().split(None, 1)
                user.first_name = parts[0]
                user.last_name = parts[1] if len(parts) > 1 else ''
            if email:
                user.email = email
            user.save()
        except Exception:
            # Do not fail profile save if user update has issues
            pass

        if commit:
            profile.save()
        return profile
