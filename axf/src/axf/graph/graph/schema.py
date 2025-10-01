from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, Protocol

from typing_extensions import NotRequired, TypedDict

if TYPE_CHECKING:
    from axf.graph.edge.schema import EdgeData
    from axf.graph.schema import ResultData
    from axf.graph.vertex.base import Vertex
    from axf.graph.vertex.schema import NodeData
    from axf.schema.log import LoggableType


class ViewPort(TypedDict):
    x: float
    y: float
    zoom: float


class GraphData(TypedDict):
    nodes: list[NodeData]
    edges: list[EdgeData]
    viewport: NotRequired[ViewPort]


class GraphDump(TypedDict, total=False):
    data: GraphData
    is_component: bool
    name: str
    description: str
    endpoint_name: str


class VertexBuildResult(NamedTuple):
    result_dict: ResultData
    params: str
    valid: bool
    artifacts: dict
    vertex: Vertex


class OutputConfigDict(TypedDict):
    cache: bool


class StartConfigDict(TypedDict):
    output: OutputConfigDict


class LogCallbackFunction(Protocol):
    def __call__(self, event_name: str, log: LoggableType) -> None: ...
