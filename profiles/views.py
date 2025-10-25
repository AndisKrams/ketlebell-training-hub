from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .forms import UserProfileForm
from .models import UserProfile


@login_required
def profile_view(request):
    """Render and update the user's profile. Orders are optional."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully')
            return redirect('profiles:profile')
        messages.error(request, 'Please correct the errors below')
    else:
        form = UserProfileForm(instance=profile)

    # Load the user's orders (if any) ordered by date desc
    orders = profile.orders.all().order_by('-date')

    return render(
        request,
        'profiles/profile.html',
        {'form': form, 'orders': orders},
    )
