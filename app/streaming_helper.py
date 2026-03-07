import json
from app.core.logger import get_logger
from app.services.conversation_manager import ConversationManager

logger = get_logger(__name__)
conversation_manager = ConversationManager()

# NOTE: This module is currently unused — streaming is handled inline
# in app/main.py:stream_message(). Kept for reference only.


async def stream_conversation_message(session_id: str, user_message: str):
    """
    Generator function for streaming conversation responses.
    """
    try:
        session = conversation_manager.get_session(session_id)
        if not session:
            yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
            return

        # Add user message to history
        conversation_manager.add_message_to_history(session_id, "user", user_message)

        # Get conversation context for LLM
        from app.services.llm_service import AsyncLLMService
        async_llm = AsyncLLMService()
        
        # Build messages for LLM
        messages = conversation_manager._build_llm_messages(session_id, user_message)
        
        # Stream the response
        full_response = ""
        async for chunk in async_llm.stream_chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        ):
            full_response += chunk
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        # Process the complete response
        response = await conversation_manager._process_llm_response(
            session_id=session_id,
            llm_response=full_response
        )

        # Send completion event with metadata
        yield f"data: {json.dumps({
            'done': True,
           'is_complete': response.is_complete,
            'suggestions': response.suggestions,
            'collected_parameters': response.collected_parameters,
            'run_id': response.run_id
        })}\n\n"

    except Exception as e:
        logger.error(f"[{session_id}] Streaming error: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
