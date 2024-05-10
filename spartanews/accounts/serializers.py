from rest_framework import serializers
from django.contrib.auth import get_user_model


class OtherUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = [
            "id",
            "username",
            "date_joined",
            "introduction",
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["user_contents_url"] = f"api/content/?user={instance.id}"
        ret["user_comments_url"] = f"api/content/comment/?user={instance.id}"
        ret["favorite_contents_url"] = f"api/content/?favorite-by={instance.id}"
        return ret


class UserSerializer(OtherUserSerializer):
    
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["liked_contents_url"] = f"api/content/?liked-by={instance.id}"
        ret["liked_comments_url"] = f"api/content/comment/?liked-by={instance.id}"
        return ret