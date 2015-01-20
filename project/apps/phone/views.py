
import arrow

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render_to_response

from project.exceptions import ProjectException
from project.errorcode import ErrorCode
from apps.phone.models import Phone
from apps.phone.forms import LoginForm


def login(request):
    if request.method == 'GET':
        return render_to_response(
            "login.html",
            {'form': LoginForm().as_p()}
        )

    form = LoginForm(request.POST)
    if not form.is_valid():
        raise ProjectException(ErrorCode.REQUEST_ERROR)

    udid = form.cleaned_data['udid']
    phone = form.cleaned_data['phone']

    if Phone.objects.filter(udid=udid).exists():
        # update
        Phone.objects.filter(udid=udid).update(
            phone=phone,
            last_login=arrow.utcnow().format('YYYY-MM-DD HH:mm:ssZ')
        )
    else:
        # create new
        Phone.objects.create(
            udid=udid,
            phone=phone,
            last_login=arrow.utcnow().format('YYYY-MM-DD HH:mm:ssZ')
        )

    # set sessions
    request.session['udid'] = udid
    request.session['phone'] = phone

    # TODO
    data = {
        'ret': 0,
        'data': {
            'version': '1',
            'copyright': 'good!'
        }
    }

    return JsonResponse(data)
