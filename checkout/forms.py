from django import forms

from .models import Order


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            'full_name',
            'email',
            'phone_number',
            'country',
            'postcode',
            'town_or_city',
            'street_address1',
            'street_address2',
            'county',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'full_name': 'Full name',
            'email': 'Email address',
            'phone_number': 'Phone number',
            'postcode': 'Postal code',
            'town_or_city': 'Town or city',
            'street_address1': 'Street address 1',
            'street_address2': 'Street address 2',
            'county': 'County, state or region',
        }

        self.fields['full_name'].widget.attrs.update({'autofocus': True})
        for field_name, placeholder in placeholders.items():
            if field_name in self.fields:
                attrs = {
                    'placeholder': placeholder,
                    'class': 'border-black rounded-0',
                }
                # Add semantic autocomplete attributes for better autofill
                autocomplete_map = {
                    'full_name': 'name',
                    'email': 'email',
                    'phone_number': 'tel',
                    'street_address1': 'address-line1',
                    'street_address2': 'address-line2',
                    'town_or_city': 'address-level2',
                    'county': 'address-level1',
                    'postcode': 'postal-code',
                    'country': 'country',
                }
                ac = autocomplete_map.get(field_name)
                if ac:
                    attrs['autocomplete'] = ac
                self.fields[field_name].widget.attrs.update(attrs)
