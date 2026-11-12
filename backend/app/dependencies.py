"""Зависимости FastAPI. Сами объекты создаются в app.main.create_app и лежат в app.state."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.config import Settings
from app.repositories.game import GameRepository
from app.services.connections import ConnectionRegistry
from app.services.game import Clock
from app.services.vision import DetectGesture

# HTTPConnection — общий предок Request и WebSocket, поэтому зависимости работают в обоих.


def get_settings(connection: HTTPConnection) -> Settings:
    return connection.app.state.settings


def get_repository(connection: HTTPConnection) -> GameRepository:
    return connection.app.state.repository


def get_registry(connection: HTTPConnection) -> ConnectionRegistry:
    return connection.app.state.registry


def get_detect_gesture(connection: HTTPConnection) -> DetectGesture:
    return connection.app.state.detect_gesture


def get_clock(connection: HTTPConnection) -> Clock:
    return connection.app.state.clock


SettingsDep = Annotated[Settings, Depends(get_settings)]
RepositoryDep = Annotated[GameRepository, Depends(get_repository)]
RegistryDep = Annotated[ConnectionRegistry, Depends(get_registry)]
DetectGestureDep = Annotated[DetectGesture, Depends(get_detect_gesture)]
ClockDep = Annotated[Clock, Depends(get_clock)]
