from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.conf import settings

from .forms import ContactForm
from .models import ContactMessage, ContactSettings
from checkout.models import Order
from django.core.mail import send_mail


def _get_settings():
    try:
        return ContactSettings.objects.first()
    except Exception:
        return None


@login_required
def contact_order(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)

    # Ensure the logged-in user owns the order
    if not order.profile or order.profile.user != request.user:
        messages.error(request, 'You do not have permission to contact us about this order')
        return redirect('profiles:profile')

    # Only allow contact for paid orders and within allowed window
    if order.status != Order.STATUS_PAID:
        messages.error(request, 'You can only contact us about paid orders')
        return redirect('profiles:profile')

    cfg = _get_settings()
    days = cfg.days_after_order if cfg else 42
    cutoff = order.date + timezone.timedelta(days=days)
    if timezone.now() > cutoff:
        messages.error(request, 'The contact window for this order has expired')
        return redirect('profiles:profile')

    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            msg = ContactMessage.objects.create(
                user=request.user,
                order=order,
                subject=form.cleaned_data.get('subject') or '',
                message=form.cleaned_data.get('message'),
            )

            # Optionally copy message to configured email
            copied = False
            if cfg and cfg.forward_to_email:
                try:
                    sender = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or cfg.forward_to_email
                    send_mail(
                        f"Contact about order {order.order_number}: {msg.subject}",
                        f"From: {request.user.get_full_name()} <{request.user.email}>\n\n{msg.message}",
                        sender,
                        [cfg.forward_to_email],
                        fail_silently=False,
                    )
                    copied = True
                except Exception:
                    copied = False

            if copied:
                msg.copied_to_email = True
                msg.save()

            messages.success(request, 'Your message has been sent. We will contact you shortly.')
            return redirect('contact:contact_success')
        messages.error(request, 'Please correct the errors below')
    else:
        form = ContactForm()

    return render(request, 'contact/contact_form.html', {'form': form, 'order': order, 'days_allowed': days})


@login_required
def contact_success(request):
    return render(request, 'contact/contact_success.html')
from django.shortcuts import render

# Create your views here.
