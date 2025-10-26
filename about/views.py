from django.shortcuts import render


def about(request):
    """Simple about page for the shop."""
    return render(request, "about/about.html")


from django.shortcuts import render
