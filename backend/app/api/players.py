from fastapi import APIRouter, Response, status

from app.dependencies import RepositoryDep
from app.schemas.api import PlayerCreateRequest, PlayerResponse

router = APIRouter(tags=["players"])


@router.post(
    "/players",
    response_model=PlayerResponse,
    responses={status.HTTP_201_CREATED: {"model": PlayerResponse, "description": "Создан новый игрок"}},
)
async def create_player(
    body: PlayerCreateRequest, response: Response, repository: RepositoryDep
) -> PlayerResponse:
    """Вход по имени. Идемпотентно: если игрок с таким именем уже есть, возвращается он."""
    player, created = await repository.get_or_create_player(body.name)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return PlayerResponse(player_id=player.id, name=player.name, created_at=player.created_at)
