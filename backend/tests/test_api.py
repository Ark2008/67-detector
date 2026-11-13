import uuid

import pytest
from fastapi.testclient import TestClient

from app.models import SessionStatus
from app.repositories.game import PlayerData, SessionData
from tests.fakes import InMemoryGameRepository

# POST /players


def test_new_player_is_created(client: TestClient, repository: InMemoryGameRepository) -> None:
    response = client.post("/players", json={"name": "Петя"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"player_id", "name", "created_at"}
    assert body["name"] == "Петя"
    assert uuid.UUID(body["player_id"]) in repository.players


def test_existing_player_is_returned_by_name_ignoring_case(client: TestClient) -> None:
    created = client.post("/players", json={"name": "Петя"}).json()

    response = client.post("/players", json={"name": "  петя "})

    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.parametrize("name", ["", "   ", "x" * 51])
def test_invalid_player_name_is_rejected(client: TestClient, name: str) -> None:
    assert client.post("/players", json={"name": name}).status_code == 422


# POST /sessions


def test_session_is_started(client: TestClient, player: PlayerData) -> None:
    response = client.post("/sessions", json={"player_id": str(player.id)})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"session_id", "status", "score", "started_at"}
    assert body["status"] == "active"
    assert body["score"] == 0


def test_session_for_unknown_player_is_not_started(client: TestClient) -> None:
    response = client.post("/sessions", json={"player_id": str(uuid.uuid4())})

    assert response.status_code == 404
    assert response.json() == {"detail": "player_not_found"}


def test_session_with_invalid_player_id_is_rejected(client: TestClient) -> None:
    assert client.post("/sessions", json={"player_id": "not-a-uuid"}).status_code == 422


# POST /sessions/{session_id}/stop


def test_session_is_stopped(client: TestClient, session: SessionData) -> None:
    response = client.post(f"/sessions/{session.id}/stop")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"session_id", "status", "score", "started_at", "ended_at"}
    assert body["session_id"] == str(session.id)
    assert body["status"] == "stopped"
    assert body["ended_at"] is not None


def test_stop_is_idempotent(client: TestClient, session: SessionData) -> None:
    first = client.post(f"/sessions/{session.id}/stop").json()

    second = client.post(f"/sessions/{session.id}/stop")

    assert second.status_code == 200
    assert second.json() == first


def test_stop_of_timed_out_session_returns_its_final_state(
    client: TestClient, repository: InMemoryGameRepository, player: PlayerData
) -> None:
    session = repository.add_session(player.id, score=7, status=SessionStatus.TIMEOUT)

    body = client.post(f"/sessions/{session.id}/stop").json()

    assert body["status"] == "timeout"
    assert body["score"] == 7


def test_stop_of_unknown_session_returns_404(client: TestClient) -> None:
    response = client.post(f"/sessions/{uuid.uuid4()}/stop")

    assert response.status_code == 404
    assert response.json() == {"detail": "session_not_found"}


# GET /ratings


def test_ratings_are_sorted_by_total_score(client: TestClient, repository: InMemoryGameRepository) -> None:
    petya = repository.add_player("Петя")
    masha = repository.add_player("Маша")
    newcomer = repository.add_player("Новичок")
    repository.add_session(petya.id, score=5, status=SessionStatus.STOPPED)
    repository.add_session(petya.id, score=12, status=SessionStatus.TIMEOUT)
    repository.add_session(masha.id, score=30, status=SessionStatus.STOPPED)
    # Активная сессия в рейтинг не входит.
    repository.add_session(petya.id, score=100)

    response = client.get("/ratings")

    assert response.status_code == 200
    assert response.json() == {
        "players": [
            {"player_id": str(masha.id), "name": "Маша", "total_score": 30, "best_session_score": 30},
            {"player_id": str(petya.id), "name": "Петя", "total_score": 17, "best_session_score": 12},
            {"player_id": str(newcomer.id), "name": "Новичок", "total_score": 0, "best_session_score": 0},
        ]
    }


def test_empty_ratings(client: TestClient) -> None:
    assert client.get("/ratings").json() == {"players": []}


# CORS


def test_frontend_origin_is_allowed(client: TestClient) -> None:
    response = client.get("/ratings", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
