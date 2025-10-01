import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from axiestudio.api.v1.endpoints import consume_and_yield, run_flow_generator, simple_run_flow
from axiestudio.api.v1.schemas import SimplifiedAPIRequest
from axiestudio.events.event_manager import create_stream_tokens_event_manager
from axiestudio.helpers.flow import get_flow_by_id_or_endpoint_name
from axiestudio.schema import (
    OpenAIErrorResponse,
    OpenAIResponsesRequest,
    OpenAIResponsesResponse,
    OpenAIResponsesStreamChunk,
)
from axiestudio.schema.content_types import ToolContent
from axiestudio.services.auth.utils import api_key_security
from axiestudio.services.database.models.flow.model import FlowRead
from axiestudio.services.database.models.user.model import UserRead
from axiestudio.services.deps import get_telemetry_service
from axiestudio.services.telemetry.schema import RunPayload
from axiestudio.services.telemetry.service import TelemetryService
from axiestudio.logging import logger

router = APIRouter(tags=["OpenAI Responses API"])


def has_chat_input(flow_data: dict | None) -> bool:
    """Check if the flow has a chat input component."""
    if not flow_data or "nodes" not in flow_data:
        return False

    return any(node.get("data", {}).get("type") in ["ChatInput", "Chat Input"] for node in flow_data["nodes"])


def has_chat_output(flow_data: dict | None) -> bool:
    """Check if the flow has a chat input component."""
    if not flow_data or "nodes" not in flow_data:
        return False

    return any(node.get("data", {}).get("type") in ["ChatOutput", "Chat Output"] for node in flow_data["nodes"])


async def run_flow_for_openai_responses(
    flow: FlowRead,
    message: str,
    user_id: str,
    session_id: str | None = None,
    tweaks: dict | None = None,
    stream: bool = False,
) -> dict[str, Any] | AsyncGenerator[str, None]:
    """Run a flow and return the response in OpenAI format."""
    try:
        # Create the request
        request = SimplifiedAPIRequest(
            input_value=message,
            input_type="chat",
            output_type="chat",
            tweaks=tweaks or {},
            session_id=session_id,
        )

        if stream:
            # For streaming, we need to use the generator
            async def stream_generator():
                async for chunk in run_flow_generator(
                    flow=flow,
                    request=request,
                    user_id=user_id,
                ):
                    if chunk:
                        yield chunk
            return stream_generator()
        else:
            # For non-streaming, use simple run
            result = await simple_run_flow(
                flow=flow,
                request=request,
                user_id=user_id,
            )
            return result

    except Exception as e:
        logger.error(f"Error running flow for OpenAI responses: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


def create_openai_error(error_message: str, error_type: str = "invalid_request_error") -> OpenAIErrorResponse:
    """Create an OpenAI-formatted error response."""
    return OpenAIErrorResponse(
        error={
            "message": error_message,
            "type": error_type,
            "param": None,
            "code": None,
        }
    )


@router.post("/openai/v1/chat/completions", response_model=None)
async def openai_chat_completions(
    request: OpenAIResponsesRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[UserRead, Depends(api_key_security)],
    telemetry_service: Annotated[TelemetryService, Depends(get_telemetry_service)],
) -> OpenAIResponsesResponse | StreamingResponse:
    """
    OpenAI-compatible chat completions endpoint.
    
    This endpoint provides OpenAI API compatibility for Axie Studio flows.
    """
    try:
        # Get the flow
        flow = await get_flow_by_id_or_endpoint_name(
            flow_id_or_name=request.model,
            user_id=str(current_user.id),
        )
        
        if not flow:
            error_response = create_openai_error(f"Flow '{request.model}' not found")
            raise HTTPException(status_code=404, detail=error_response.model_dump())

        # Validate flow has chat components
        if not has_chat_input(flow.data) or not has_chat_output(flow.data):
            error_response = create_openai_error(
                "Flow must have both ChatInput and ChatOutput components for OpenAI compatibility"
            )
            raise HTTPException(status_code=400, detail=error_response.model_dump())

        # Extract the last message
        if not request.messages:
            error_response = create_openai_error("At least one message is required")
            raise HTTPException(status_code=400, detail=error_response.model_dump())

        last_message = request.messages[-1]
        message_content = last_message.content

        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())

        # Log telemetry
        run_payload = RunPayload(
            flow_id=str(flow.id),
            flow_name=flow.name,
            user_id=str(current_user.id),
        )
        background_tasks.add_task(telemetry_service.log_run, run_payload)

        if request.stream:
            # Streaming response
            async def generate_stream():
                try:
                    async for chunk in run_flow_for_openai_responses(
                        flow=flow,
                        message=message_content,
                        user_id=str(current_user.id),
                        session_id=session_id,
                        tweaks=request.tweaks,
                        stream=True,
                    ):
                        if chunk:
                            # Convert to OpenAI streaming format
                            openai_chunk = OpenAIResponsesStreamChunk(
                                id=f"chatcmpl-{uuid.uuid4()}",
                                object="chat.completion.chunk",
                                created=int(time.time()),
                                model=request.model,
                                choices=[{
                                    "index": 0,
                                    "delta": {"content": chunk},
                                    "finish_reason": None,
                                }],
                            )
                            yield f"data: {openai_chunk.model_dump_json()}\n\n"
                    
                    # Send final chunk
                    final_chunk = OpenAIResponsesStreamChunk(
                        id=f"chatcmpl-{uuid.uuid4()}",
                        object="chat.completion.chunk",
                        created=int(time.time()),
                        model=request.model,
                        choices=[{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }],
                    )
                    yield f"data: {final_chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"
                    
                except Exception as e:
                    logger.error(f"Error in streaming: {e}")
                    error_chunk = create_openai_error(str(e))
                    yield f"data: {error_chunk.model_dump_json()}\n\n"

            return StreamingResponse(
                generate_stream(),
                media_type="text/plain",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/plain; charset=utf-8",
                },
            )
        else:
            # Non-streaming response
            result = await run_flow_for_openai_responses(
                flow=flow,
                message=message_content,
                user_id=str(current_user.id),
                session_id=session_id,
                tweaks=request.tweaks,
                stream=False,
            )

            # Extract response content
            response_content = ""
            if isinstance(result, dict):
                # Handle different response formats
                if "outputs" in result:
                    outputs = result["outputs"]
                    if outputs and len(outputs) > 0:
                        first_output = outputs[0]
                        if "outputs" in first_output:
                            output_data = first_output["outputs"]
                            if output_data and len(output_data) > 0:
                                first_data = output_data[0]
                                if "results" in first_data:
                                    results = first_data["results"]
                                    if "message" in results:
                                        response_content = results["message"].get("text", "")

            # Create OpenAI response
            openai_response = OpenAIResponsesResponse(
                id=f"chatcmpl-{uuid.uuid4()}",
                object="chat.completion",
                created=int(time.time()),
                model=request.model,
                choices=[{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_content,
                    },
                    "finish_reason": "stop",
                }],
                usage={
                    "prompt_tokens": len(message_content.split()),
                    "completion_tokens": len(response_content.split()),
                    "total_tokens": len(message_content.split()) + len(response_content.split()),
                },
            )

            return openai_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in OpenAI chat completions: {e}")
        error_response = create_openai_error(f"Internal server error: {str(e)}")
        raise HTTPException(status_code=500, detail=error_response.model_dump()) from e
