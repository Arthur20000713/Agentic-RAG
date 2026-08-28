from __future__ import annotations

from fastapi import APIRouter, Header, Path, Query, Request

from backend.app.agent.checkpointing import checkpoint_thread_id
from backend.app.core.errors import ErrorCode
from backend.app.core.response import ApiResponse
from backend.app.db.repositories import ConversationRepository
from backend.app.schemas.api import ConversationRenameRequest


router = APIRouter(prefix="/api/conversations", tags=["conversations"])
IDENTIFIER_PATTERN = r"^[A-Za-z0-9._-]+$"


def _repository(request: Request) -> ConversationRepository:
    return ConversationRepository(request.app.state.db_conn)


@router.get("")
async def list_conversations(
    request: Request,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    client_id: str = Header(
        default="anonymous",
        alias="X-Client-ID",
        max_length=128,
        pattern=IDENTIFIER_PATTERN,
    ),
) -> dict:
    items, total = _repository(request).list(
        client_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return ApiResponse.ok({"items": items, "total": total, "limit": limit, "offset": offset}).model_dump()


@router.get("/{session_id}")
async def get_conversation(
    request: Request,
    session_id: str = Path(max_length=128, pattern=IDENTIFIER_PATTERN),
    client_id: str = Header(
        default="anonymous", alias="X-Client-ID", max_length=128, pattern=IDENTIFIER_PATTERN
    ),
) -> dict:
    repository = _repository(request)
    conversation = repository.get(session_id, client_id)
    if conversation is None:
        return ApiResponse.fail(ErrorCode.NOT_FOUND, "conversation not found").model_dump()
    return ApiResponse.ok(
        {"conversation": conversation, "messages": repository.messages(session_id, client_id)}
    ).model_dump()


@router.patch("/{session_id}")
async def rename_conversation(
    payload: ConversationRenameRequest,
    request: Request,
    session_id: str = Path(max_length=128, pattern=IDENTIFIER_PATTERN),
    client_id: str = Header(
        default="anonymous", alias="X-Client-ID", max_length=128, pattern=IDENTIFIER_PATTERN
    ),
) -> dict:
    repository = _repository(request)
    if not repository.rename(session_id, client_id, payload.title):
        return ApiResponse.fail(ErrorCode.NOT_FOUND, "conversation not found").model_dump()
    return ApiResponse.ok(repository.get(session_id, client_id)).model_dump()


@router.delete("/{session_id}")
async def delete_conversation(
    request: Request,
    session_id: str = Path(max_length=128, pattern=IDENTIFIER_PATTERN),
    client_id: str = Header(
        default="anonymous", alias="X-Client-ID", max_length=128, pattern=IDENTIFIER_PATTERN
    ),
) -> dict:
    if not _repository(request).delete(session_id, client_id):
        return ApiResponse.fail(ErrorCode.NOT_FOUND, "conversation not found").model_dump()
    checkpointer = getattr(request.app.state, "agent_checkpointer", None)
    if checkpointer is not None:
        await checkpointer.adelete_thread(checkpoint_thread_id(client_id, session_id))
    return ApiResponse.ok({"session_id": session_id, "deleted": True}).model_dump()
