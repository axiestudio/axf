from axiestudio.services.base import Service
from axiestudio.services.factory import ServiceFactory
from axiestudio.services.job_queue.service import JobQueueService


class JobQueueServiceFactory(ServiceFactory):
    def __init__(self):
        super().__init__(JobQueueService)

    def create(self) -> Service:
        return JobQueueService()
