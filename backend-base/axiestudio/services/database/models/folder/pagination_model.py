from fastapi_pagination import Page

from axiestudio.helpers.base_model import BaseModel
from axiestudio.services.database.models.flow.model import Flow
from axiestudio.services.database.models.folder.model import FolderRead


class FolderWithPaginatedFlows(BaseModel):
    folder: FolderRead
    flows: Page[Flow]
