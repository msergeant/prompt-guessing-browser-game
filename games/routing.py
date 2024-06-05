from django.urls import re_path

from . import consumers

websocket_url_patterns = [
    re_path(r"ws/game/(?P<code>\w+)/$",
            consumers.RunningGameConsumer.as_asgi())
]
