from django.http import HttpResponse


def webhook_stub(request):
    """A placeholder webhook endpoint for payment provider callbacks.

    This currently accepts any request and returns 200. Replace with
    provider-specific verification and event handling as needed.
    """
    return HttpResponse(status=200)
