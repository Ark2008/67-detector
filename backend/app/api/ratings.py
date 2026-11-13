from fastapi import APIRouter

from app.dependencies import RepositoryDep
from app.schemas.api import RatingPlayer, RatingsResponse

router = APIRouter(tags=["ratings"])


@router.get("/ratings", response_model=RatingsResponse)
async def get_ratings(repository: RepositoryDep) -> RatingsResponse:
    """Рейтинг игроков по сумме очков завершённых сессий, по убыванию."""
    rows = await repository.get_ratings()
    return RatingsResponse(
        players=[
            RatingPlayer(
                player_id=row.player_id,
                name=row.name,
                total_score=row.total_score,
                best_session_score=row.best_session_score,
            )
            for row in rows
        ]
    )
