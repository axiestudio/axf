from typing import TYPE_CHECKING

from typing_extensions import override

from axiestudio.services.factory import ServiceFactory
from axiestudio.services.socket.service import SocketIOService

if TYPE_CHECKING:
    from axiestudio.services.cache.service import CacheService


class SocketIOFactory(ServiceFactory):
    def __init__(self) -> None:
        super().__init__(
            service_class=SocketIOService,
        )

    @override
    def create(self, cache_service: "CacheService"):
        return SocketIOService(cache_service)
