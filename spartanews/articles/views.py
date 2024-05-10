# Django modules
from django.contrib.auth import get_user_model
from django.db.models import (
    F, Count, Func, ExpressionWrapper,
    DateTimeField,
    DurationField,
    IntegerField,
)
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404
from django.utils import timezone

# DRF modules
from rest_framework import status, generics
from rest_framework.decorators import api_view
from rest_framework.exceptions import APIException
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly

# serializers and models
from .serializers import (
    ContentSerializer,
    ContentAllSerializer,
    CommentSerializer,
)
from .models import ContentInfo, CommentInfo


# Custom API exception class when request with unavailable query params
class InvalidQueryParamsException(APIException): # exception 모델 상속 받아서 커스텀한 것 overriding
    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = "Your request contain invalid query parameters."


# Custom pagination class for articles list
class ArticlesListPagination(PageNumberPagination): # 페이지네이션 커스텀
    page_size = 20
    page_size_query_param = 'page_size' # 20에서 100 사이로
    max_page_size = 100


# Custom pagination class for an article's comments list
class CommentsListPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 50


class ContentListAPIView(generics.ListAPIView):
    serializer_class = ContentAllSerializer # serializers.py에서 상속
    pagination_class = ArticlesListPagination # 페이지네이션 구현 custom pagination을 함
    permission_classes = [IsAuthenticatedOrReadOnly] 

    def get_queryset(self): #
        query_params = self.request.query_params # 쿼리 파라미터 담기

        # value of ordering query string
        order_by = query_params.get("order-by") # 꺼내기

        # value of filtering query string
        favorite_by = query_params.get("favorite-by") #UserInfo로
        liked_by = query_params.get("liked-by") #UserInfo로
        user = query_params.get("user")

        # Filtering

        # check 'favorite_by' query string
        # UserInfo.favorite_contents
        if favorite_by:
            if favorite_by.isdecimal():
                rows = get_user_model().objects.get(pk=int(favorite_by)).favorite_contents.filter(is_visible=True) # 그 유저가 즐찾한 글을 모두 들고와서 거기에서 favorite 컨텐츠를 뽑고 존재(is_visible=True) 하는 걸 불러오기
            else:
                raise InvalidQueryParamsException
        # check 'liked_by' query string
        # UserInfo.liked_contents
        elif liked_by:
            if liked_by.isdecimal():
                rows = get_user_model().objects.get(pk=int(liked_by)).liked_contents.filter(is_visible=True)
            else:
                raise InvalidQueryParamsException
        # check 'user' query string
        # ContentInfo
        elif user:
            if user.isdecimal():
                rows = ContentInfo.objects.filter(is_visible=True, userinfo_id=int(user)) 
            else:
                raise InvalidQueryParamsException
        # no query string
        # ContentInfo
        else:
            rows = ContentInfo.objects.filter(is_visible=True) # 모든 content를 불러옴

        # annotate fields: 'comment_count', 'like_count', 'article_point'
        # annotate but not include in serialized data: 'duration_in_microseconds', 'duration'
        # duration_in_microseconds is divided by (1000 * 1000 * 60 * 60 * 24)
        # because of converting microseconds to days

        # duration Extract 사용은 duration... extract 는 장고의 기능임. duration_in_microseconds로 변환
        rows = rows.annotate(
            comment_count=Count(F("comments_on_content")), # 역참조 CommentInfo에서 역참조 매니저 명
            like_count=Count(F("liked_by")), # 역참조 UserInfo에서 역참조 매니저명
            duration_in_microseconds=ExpressionWrapper(
                Cast(timezone.now().replace(microsecond=0), DateTimeField()) - F("create_dt"),
                output_field=DurationField()
            )
        ).annotate(
            duration=ExpressionWrapper(
                Func(
                    F('duration_in_microseconds') / (1000 * 1000 * 60 * 60 * 24),
                    function='FLOOR',
                    template="%(function)s(%(expressions)s)"
                ), # microseconds -> days 로 변환 #Func(): 데이터베이스의 함수를 직접 작성해서 쓸 수 있게. 장고가 지원함.
                output_field=IntegerField()
            ) #// 여기까지는 SQLite의 한계로... 어쩔 수 없이 변환해서 씀
        ).annotate(
            article_point=ExpressionWrapper(
                -5 * F("duration") + 3 * F("comment_count") + F("like_count"),
                output_field=IntegerField()
            )
        ) # 시리얼라이저로 반환해서 정렬하기 어려우므로 필드 추가를 해서 반환. 시리얼라이저에서 할지 뷰에서 할지 방법 중 뷰에서 하는 걸로 선택한 것.
        # annotate의 좋은 점: 데이터베이스에는 포함이 안 됨. 임시로 필드를 생성해서.

        # Ordering
        # order-by=new: ORDER BY create_dt DESC
        # nothing: ORDER BY article_point DESC create_dt DESC
        if order_by == "new":
            rows = rows.order_by("-create_dt") # 최신순
        else:
            rows = rows.order_by("-article_point", "-create_dt")

        return rows # queryset return

    def post(self, request):
        serializer = ContentSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save(
                userinfo=request.user,
                is_visible=True
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)


class ContentDetailAPIView(generics.ListAPIView):
    serializer_class = ContentAllSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_row(self, content_id):
        return get_object_or_404(ContentInfo, pk=content_id)

    def get_queryset(self):
        row = ContentInfo.objects.filter(pk=self.kwargs.get("content_id"), is_visible=True)
        if not row:
            return ContentInfo.objects.none()

        # annotate fields: 'comment_count', 'like_count', 'article_point'
        # annotate but not include in serialized data: 'duration_in_microseconds', 'duration'
        # duration_in_microseconds is divided by (1000 * 1000 * 60 * 60 * 24)
        # because of converting microseconds to days
        row = row.annotate(
            comment_count=Count(F("comments_on_content")),
            like_count=Count(F("liked_by")),
            duration_in_microseconds=ExpressionWrapper(
                Cast(timezone.now().replace(microsecond=0), DateTimeField()) - F("create_dt"),
                output_field=DurationField()
            )
        ).annotate(
            duration=ExpressionWrapper(
                Func(
                    F('duration_in_microseconds') / (1000 * 1000 * 60 * 60 * 24),
                    function='FLOOR',
                    template="%(function)s(%(expressions)s)"
                ),
                output_field=IntegerField()
            )
        ).annotate(
            article_point=ExpressionWrapper(
                -5 * F("duration") + 3 * F("comment_count") + F("like_count"),
                output_field=IntegerField()
            )
        )

        return row
    
    def put(self, request, content_id):
        row = self.get_row(content_id)
        # 로그인한 사용자와 글 작성자가 다를 경우 상태코드 403
        if request.user.id != row.userinfo.id:
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = ContentSerializer(row, data=request.data, partial=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data)

    def delete(self, request, content_id):
        row = self.get_row(content_id)
        # 로그인한 사용자와 글 작성자가 다를 경우 상태코드 403
        if request.user.id != row.userinfo.id:
            return Response(status=status.HTTP_403_FORBIDDEN)

        # soft delete
        # 삭제된 글 추적을 위함
        row.is_visible = False
        row.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentListAPIView(generics.ListAPIView):
    serializer_class = CommentSerializer
    pagination_class = CommentsListPagination
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self): #get_queryset은 파라미터를 받을 수 없음.
        # endpoint: /api/content/<int:content_id>/comment
        content_id = self.kwargs.get("content_id")
        # check 'content_id' parameter
        # CommentInfo
        if content_id: #content_id가 있으면
            rows = CommentInfo.objects.filter(contentinfo_id=content_id, is_visible=True) # 리스트에 담아서 주어야 해서 이렇게 함. QueryDict로
            # order by earliest
            return rows.order_by("create_dt") # queryset으로 던지기 때문에 Response 안 씀

        # endpoint: /api/content/comment
        liked_by = self.request.GET.get("liked-by")
        user = self.request.GET.get("user")
        # check 'liked_by' query string
        # UserInfo.liked_comments
        if liked_by:
            if liked_by.isdecimal():
                rows = get_user_model().objects.get(pk=int(liked_by)).liked_comments.filter(is_visible=True)
            else:
                raise InvalidQueryParamsException
        # check 'user' query string
        # CommentInfo
        elif user:
            if user.isdecimal():
                rows = CommentInfo.objects.filter(is_visible=True, userinfo_id=int(user))
            else:
                raise InvalidQueryParamsException
        # no query string
        # CommentInfo
        else:
            rows = CommentInfo.objects.filter(is_visible=True)

        # order by latest
        return rows.order_by("-create_dt")

    def post(self, request, content_id):
        serializer = CommentSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save(
                userinfo=request.user,
                contentinfo=ContentInfo.objects.get(pk=content_id),
                is_visible=True
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)


class CommentDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_row(self, comment_id):
        return get_object_or_404(CommentInfo, pk=comment_id)

    def put(self, request, comment_id):
        row = self.get_row(comment_id)
        # 로그인한 사용자와 댓글 작성자가 다를 경우 상태코드 403
        if request.user.id != row.userinfo.id:
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = CommentSerializer(row, data=request.data, partial=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

    def delete(self, request, comment_id):
        row = self.get_row(comment_id)
        # 로그인한 사용자와 댓글 작성자가 다를 경우 상태코드 403
        if request.user.id != row.userinfo.id:
            return Response(status=status.HTTP_403_FORBIDDEN)

        # soft delete
        # 삭제된 댓글 추적을 위함
        row.is_visible = False
        row.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

# FBV로 구현

@api_view(["POST"])
def content_favorite(request, content_id):
    if request.user.is_authenticated: # 한결 튜터님 피드백: 데코레이터로.. 해진님은 에러가 계속 발생해서 이렇게 처리하셨다고
        me = get_user_model().objects.get(id=request.user.id)
        content = get_object_or_404(ContentInfo, id=content_id)

        if me.favorite_contents.filter(id=content_id).exists():
            me.favorite_contents.remove(content)
            return Response(
                data={
                    "message": "Favorite content canceled.",
                },
                status=status.HTTP_200_OK
            )
        else:
            me.favorite_contents.add(content)
            return Response(
                data={
                    "message": "Favorite content success.",
                    "user": me.username,
                    "content_id": content.id,
                },
                status=status.HTTP_200_OK
            )
    else:
        return Response(status=status.HTTP_403_FORBIDDEN)


@api_view(["POST"])
def content_like(request, content_id):
    if request.user.is_authenticated:
        me = get_user_model().objects.get(id=request.user.id)
        content = get_object_or_404(ContentInfo, id=content_id)

        if me.liked_contents.filter(id=content_id).exists():
            me.liked_contents.remove(content)
            return Response(
                data={
                    "message": "Like content canceled.",
                },
                status=status.HTTP_200_OK
            )
        else:
            me.liked_contents.add(content)
            return Response(
                data={
                    "message": "Like content success.",
                    "user": me.username,
                    "content_id": content.id,
                },
                status=status.HTTP_200_OK
            )
    else:
        return Response(status=status.HTTP_403_FORBIDDEN)


@api_view(["POST"])
def comment_like(request, comment_id):
    if request.user.is_authenticated:
        me = get_user_model().objects.get(id=request.user.id)
        comment = get_object_or_404(CommentInfo, id=comment_id)

        if me.liked_comments.filter(id=comment_id).exists():
            me.liked_comments.remove(comment)
            return Response(
                data={
                    "message": "Like comment canceled.",
                },
                status=status.HTTP_200_OK
            )
        else:
            me.liked_comments.add(comment)
            return Response(
                data={
                    "message": "Like comment success.",
                    "user": me.username,
                    "content_id": comment.id,
                },
                status=status.HTTP_200_OK
            )
    else:
        return Response(status=status.HTTP_403_FORBIDDEN)
