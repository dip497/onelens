from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from ag_ui.core import RunAgentInput, EventType, RunStartedEvent, RunFinishedEvent, TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent
from ag_ui.encoder import EventEncoder
from dotenv import load_dotenv
from app.agents import get_onelens_assistant
import json
import uuid

router = APIRouter()

load_dotenv()
# Get the OneLens AI Assistant agent from centralized definitions
onelens_agent = get_onelens_assistant()

@router.post("/agent")
async def agent_endpoint(request: Request):
    """AG-UI compatible agent endpoint"""
    try:
        # Parse the request body
        body = await request.body()
        input_data = json.loads(body)

        # Extract messages from the request
        messages = input_data.get("messages", [])
        if not messages:
            return {"error": "No messages provided"}

        # Get the latest user message
        user_message = messages[-1]["content"] if messages else ""

        # Create event encoder
        encoder = EventEncoder()

        async def generate_response():
            # Generate run and message IDs
            run_id = str(uuid.uuid4())
            thread_id = input_data.get("threadId", str(uuid.uuid4()))
            message_id = str(uuid.uuid4())

            # Emit RUN_STARTED event
            run_started = RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=thread_id,
                run_id=run_id
            )
            yield encoder.encode(run_started)

            # Emit TEXT_MESSAGE_START event
            msg_start = TextMessageStartEvent(
                type=EventType.TEXT_MESSAGE_START,
                message_id=message_id,
                role="assistant"
            )
            yield encoder.encode(msg_start)

            # Get response from Agno agent
            response = onelens_agent.run(user_message, stream=True)

            # Stream the response content
            for chunk in response:
                if hasattr(chunk, 'content') and chunk.content:
                    content_event = TextMessageContentEvent(
                        type=EventType.TEXT_MESSAGE_CONTENT,
                        message_id=message_id,
                        delta=chunk.content
                    )
                    yield encoder.encode(content_event)

            # Emit TEXT_MESSAGE_END event
            msg_end = TextMessageEndEvent(
                type=EventType.TEXT_MESSAGE_END,
                message_id=message_id
            )
            yield encoder.encode(msg_end)

            # Emit RUN_FINISHED event
            run_finished = RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=thread_id,
                run_id=run_id
            )
            yield encoder.encode(run_finished)

        return StreamingResponse(
            generate_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
        )

    except Exception as e:
        return {"error": str(e)}