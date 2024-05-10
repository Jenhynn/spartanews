from rest_framework import serializers
from .models import ContentInfo, CommentInfo


class ContentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="userinfo.username", read_only=True)

    class Meta:
        model = ContentInfo
        fields = '__all__'
        read_only_fields = (
            "userinfo",
            "is_visible",
        )

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret.pop("userinfo")
        ret.pop("is_visible")
        return ret


class ContentAllSerializer(ContentSerializer):
    comment_count = serializers.IntegerField()
    like_count = serializers.IntegerField()
    article_point = serializers.IntegerField()


class CommentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="userinfo.username", read_only=True)
    likes = serializers.IntegerField(source="liked_by.count", read_only=True) # 역참조. 좋아요 수

    class Meta:
        model = CommentInfo
        fields = '__all__'
        read_only_fields = (
            "userinfo",
            "contentinfo",
            "is_visible",
        )

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret.pop("userinfo")
        ret.pop("contentinfo")
        ret.pop("is_visible")
        return ret
