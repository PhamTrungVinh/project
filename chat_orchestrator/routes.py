"""Phase 5 chat and explicit pending-action endpoints."""

import json
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session

from confirmation import execute_confirmed_tool_call
from database import get_db, get_db_session
from dependencies import get_current_claims
from shared_platform.auth_claims import AuthClaims
from schemas.chat import (
    ChatMessageRequest, ChatMessageResponse, PendingActionDecisionRequest,
    PendingActionDecisionResponse, PendingActionOut,
)
from services import chat_orchestration_service as chat_service, pending_action_service
from services.thread_lock import thread_turn_lock
from crud import conversation as conv_crud
from schemas.chat import ConversationOut, ConversationHistoryOut
from services.conversation_history_service import get_conversation_history, delete_conversation
from services.chat_stream_service import stream_turn


router = APIRouter(prefix="/v1", tags=["chat-orchestrator"])


@router.get("/chat/conversations", response_model=list[ConversationOut])
def list_conversations(
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: AuthClaims = Depends(get_current_claims),
):
    return conv_crud.list_conversations(db, current_user.id, skip=skip, limit=limit)


@router.get("/chat/conversations/{thread_id}/messages", response_model=ConversationHistoryOut)
def conversation_history(
    thread_id: str, db: Session = Depends(get_db),
    current_user: AuthClaims = Depends(get_current_claims),
):
    conversation, history = get_conversation_history(db, current_user.id, thread_id)
    return ConversationHistoryOut(**ConversationOut.model_validate(conversation).model_dump(), **history)


@router.delete("/chat/conversations/{thread_id}", status_code=204, response_class=Response)
def remove_conversation(
    thread_id: str, db: Session = Depends(get_db),
    current_user: AuthClaims = Depends(get_current_claims),
):
    delete_conversation(db, current_user.id, thread_id)
    return Response(status_code=204)


def _correlation_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or request.state.correlation_id


@router.post("/chat/messages", response_model=ChatMessageResponse)
def send_message(
    data: ChatMessageRequest, request: Request,
    db: Session = Depends(get_db), current_user: AuthClaims = Depends(get_current_claims),
):
    thread_id = data.thread_id or f"session-{uuid.uuid4().hex}"
    result = chat_service.send_message(db, current_user, thread_id, data.message)
    pending = pending_action_service.pending_for_thread(db, current_user.id, thread_id)
    return ChatMessageResponse(
        **result,
        pending_actions=[
            PendingActionOut(id=action.id, agent=action.agent, question=action.question,
                             expires_at=action.expires_at)
            for action in pending
        ],
        correlation_id=_correlation_id(request),
    )


@router.post("/chat/messages/stream", response_class=StreamingResponse,
             responses={200: {"content": {"text/event-stream": {}}}})
def stream_message(
    data: ChatMessageRequest, request: Request,
    db: Session = Depends(get_db, scope="function"), current_user: AuthClaims = Depends(get_current_claims),
):
    thread_id = data.thread_id or f"session-{uuid.uuid4().hex}"
    # Reject known ownership violations before sending streaming response headers.
    if conv_crud.get_conversation(db, thread_id) is not None:
        conv_crud.get_user_conversation(db, current_user.id, thread_id)
    correlation_id = _correlation_id(request)

    def run_turn(on_delta):
        # The request dependency may be closed before streaming finishes.
        with get_db_session() as worker_db:
            result = chat_service.send_message(worker_db, current_user, thread_id,
                                               data.message, on_delta=on_delta)
            pending = pending_action_service.pending_for_thread(worker_db, current_user.id, thread_id)
            return ChatMessageResponse(
                **result, correlation_id=correlation_id,
                pending_actions=[PendingActionOut(id=action.id, agent=action.agent,
                    question=action.question, expires_at=action.expires_at) for action in pending],
            )

    return StreamingResponse(
        stream_turn(run_turn, thread_id, correlation_id), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/pending-actions/{action_id}/decision", response_model=PendingActionDecisionResponse)
def decide_pending_action(
    action_id: str, data: PendingActionDecisionRequest, request: Request,
    db: Session = Depends(get_db), current_user: AuthClaims = Depends(get_current_claims),
):
    def execute(action):
        return execute_confirmed_tool_call(
            action.agent, current_user.id, action.thread_id,
            {"name": action.action_name, "args": json.loads(action.arguments_json)},
            action.idempotency_key, raise_errors=True, claims=current_user,
        )

    with thread_turn_lock(current_user.id, pending_action_service.thread_for_action(db, current_user.id, action_id)):
        action = pending_action_service.resolve(
            db, current_user.id, None, action_id,
            data.decision == "approve", execute,
        )
        continuation = chat_service.continue_after_decision(db, action)
        pending = pending_action_service.pending_for_thread(db, current_user.id, action.thread_id)
    return PendingActionDecisionResponse(
        id=action.id, status=action.status, thread_id=action.thread_id,
        result=action.execution_result, **continuation,
        pending_actions=[PendingActionOut(id=item.id, agent=item.agent, question=item.question,
                                          expires_at=item.expires_at) for item in pending],
        correlation_id=_correlation_id(request),
    )
