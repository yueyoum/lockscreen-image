# -*- coding: utf-8 -*-


from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render_to_response
from django.db import connection
from django.db import transaction
from django.db.models import Q
from django.db import DataError
from django.views.generic import View


from apps.image.models import ForegroundCategory, ImageBackground, ImageForeground, ImagePairForCollect, ImagePairForDownload
from apps.image.forms import ImagePairForm

from project.exceptions import ProjectException
from project.errorcode import ErrorCode

def get_foregound_category(request):
    # 获取前景分类
    categories = ForegroundCategory.objects.all()
    def _make_data(c):
        return {
            'ID': c.id,
            'name': c.name,
            'icon': c.image_url,
        }

    data = [_make_data(c) for c in categories]
    data = {
        'ret': 0,
        'data': data
    }
    return JsonResponse(data)



class ImageGetterView(object):
    BUCKET_SIZE = 45

    def __init__(self, request):
        self.request = request
        self.bucket = int(request.GET.get('bucket', 0))
        self.category = int(request.GET.get('category', 0))
        if self.category == 1:
            # all
            self.category = 0

        self.phone = request.session['phone']

        if request.path.endswith('/hot/'):
            self.order_by = 'score desc'
        else:
            self.order_by = 'upload_at desc'

        if self.bucket < 0:
            raise ProjectException(ErrorCode.REQUEST_ERROR)


    def build_sql_for_foreground(self):
        if self.category:
            sql = "select id, images->>%s as image_key from {0} where (images->>%s) is not null and array[%s] <@ categories order by {1} offset %s limit %s".format(ImageForeground._meta.db_table, self.order_by)
            params = (self.phone, self.phone, self.category, self.bucket*self.BUCKET_SIZE, self.BUCKET_SIZE)
        else:
            sql = "select id, images->>%s as image_key from {0} where (images->>%s) is not null order by {1} offset %s limit %s".format(ImageForeground._meta.db_table, self.order_by)
            params = (self.phone, self.phone, self.bucket*self.BUCKET_SIZE, self.BUCKET_SIZE)

        return sql, params

    def build_sql_for_background(self):
        sql = "select id, images->>%s as image_key from {0} where (images->>%s) is not null order by {1} offset %s limit %s".format(ImageBackground._meta.db_table,  self.order_by)
        params = (self.phone, self.phone, self.bucket*self.BUCKET_SIZE, self.BUCKET_SIZE)
        return sql, params


    def get(self):
        if self.request.path.startswith('/foreground/'):
            sql, parms = self.build_sql_for_foreground()
        else:
            sql, parms = self.build_sql_for_background()

        print sql
        print parms
        with connection.cursor() as c:
            c.execute(sql, parms)
            result = c.fetchall()

        if len(result) == self.BUCKET_SIZE:
            next_bucket = self.bucket + 1
        else:
            next_bucket = None

        def _make_image(record):
            _id = str(record[0])
            _url = settings.QINIU_DOMAIN + record[1]
            return {
                'ID': _id,
                'url': _url,
            }

        images = [_make_image(record) for record in result]
        data = {
            'ret': 0,
            'data': {
                'next_bucket_id': next_bucket,
                'images': images
            }
        }

        return JsonResponse(data)


    @classmethod
    def as_view(cls):
        def wrapper(request):
            try:
                self = cls(request)
            except:
                raise ProjectException(ErrorCode.REQUEST_ERROR)

            return self.get()
        return wrapper


class ImagePairView(View):
    def get(self, request):
        return render_to_response(
            "test.html",
            {
                'action': request.path,
                'form': ImagePairForm().as_p()
            }
        )

    def post(self, request):
        form = ImagePairForm(request.POST)
        if not form.is_valid():
            raise ProjectException(ErrorCode.REQUEST_ERROR)

        form_data = form.cleaned_data
        background_id = form_data['background']
        foreground_id = form_data['foreground']

        try:
            if not ImageBackground.objects.filter(id=background_id).exists():
                raise ProjectException(ErrorCode.BACKGROUND_NOT_EXIST)

            if not ImageForeground.objects.filter(id=foreground_id).exists():
                raise ProjectException(ErrorCode.FOREGROUND_NOT_EXIST)
        except DataError as e:
            print e
            raise ProjectException(ErrorCode.REQUEST_ERROR)


        if request.path == '/collect/':
            self.post_collect(request, background_id, foreground_id)
        elif request.path == '/uncollect/':
            self.post_uncollect(request, background_id, foreground_id)
        else:
            self.post_download(request, background_id, foreground_id)

        return JsonResponse({'ret': 0})


    def post_collect(self, request, background_id, foreground_id):
        # 收藏
        udid = request.session['udid']

        condition = Q(phone_udid=udid) & Q(background_id=background_id) & Q(foreground_id=foreground_id)
        if ImagePairForCollect.objects.filter(condition).exists():
            return

        ImagePairForCollect.objects.create(
            phone_udid=udid,
            background_id=background_id,
            foreground_id=foreground_id
        )

        self.incr_background_score(background_id)
        self.incr_foreground_score(foreground_id)


    def post_uncollect(self, request, background_id, foreground_id):
        # 取消收藏
        udid = request.session['udid']

        condition = Q(phone_udid=udid) & Q(background_id=background_id) & Q(foreground_id=foreground_id)

        pair = ImagePairForCollect.objects.filter(condition)
        if not pair.exists():
            raise ProjectException(ErrorCode.COLLECTION_PAIR_NOT_EXIST)

        pair.delete()

        self.incr_background_score(background_id, value=-1)
        self.incr_foreground_score(foreground_id, value=-1)


    def post_download(self, request, background_id, foreground_id):
        # 下载
        udid = request.session['udid']

        condition = Q(phone_udid=udid) & Q(background_id=background_id) & Q(foreground_id=foreground_id)

        if ImagePairForDownload.objects.filter(condition).exists():
            return

        ImagePairForDownload.objects.create(
            phone_udid=udid,
            background_id=background_id,
            foreground_id=foreground_id
        )

        self.incr_background_score(background_id)
        self.incr_foreground_score(foreground_id)



    def incr_background_score(self, background_id, value=1):
        with transaction.atomic():
            image = ImageBackground.objects.select_for_update().get(id=background_id)
            image.score += value
            if image.score < 0:
                image.score = 0
            image.save()


    def incr_foreground_score(self, foreground_id, value=1):
        with transaction.atomic():
            image = ImageForeground.objects.select_for_update().get(id=foreground_id)
            image.score += value
            if image.score < 0:
                image.score = 0
            image.save()
