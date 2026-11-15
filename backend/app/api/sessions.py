import uuid

from fastapi import APIRouter, HTTPException, status

from app.dependencies import RegistryDep, RepositoryDep
from app.schemas.api import SessionCreateRequest, SessionStartedResponse, SessionStoppedResponse

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=SessionStartedResponse, status_code=status.HTTP_201_CREATED)
async def start_session(body: SessionCreateRequest, repository: RepositoryDep) -> SessionStartedResponse:
    """Кнопка «Старт»: новая активная сессия игрока."""
    session = await repository.create_session(body.player_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "player_not_found")
    return SessionStartedResponse(
        session_id=session.id, status=session.status, score=session.score, started_at=session.started_at
    )


@router.post("/sessions/{session_id}/stop", response_model=SessionStoppedResponse)
async def stop_session(
    session_id: uuid.UUID, repository: RepositoryDep, registry: RegistryDep
) -> SessionStoppedResponse:
    """Кнопка «Стоп». Идемпотентно: для уже завершённой сессии возвращается её итог."""
    session = await repository.stop_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session_not_found")
    # Клиент получает session_state в сокет, после чего сокет закрывается.
    await registry.close_session(session)
    return SessionStoppedResponse(
        session_id=session.id,
        status=session.status,
        score=session.score,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )
