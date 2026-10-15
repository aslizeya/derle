from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from derle.config import Settings
from derle.llm.base import LLMProvider
from derle.storage.db import Database


def get_db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_llm(request: Request) -> LLMProvider:
    llm: LLMProvider = request.app.state.llm
    return llm


DbDep = Annotated[Database, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
LlmDep = Annotated[LLMProvider, Depends(get_llm)]
