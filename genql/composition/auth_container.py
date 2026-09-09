"""Auth and thread-history providers: the GoTrue JWT verifier and every
repository Tasks 9-14 depend on.

Extends EvalContainer rather than adding to it in place, matching the
split-by-bounded-context convention the rest of genql/composition/ follows.
All repositories reuse CoreContainer.semantic_engine — this is the same
ParadeDB/Postgres instance the catalog and semantic store already use, not a
second database. No password hasher, no OAuth client providers, no token
issuer: GoTrue is a separate process this container never talks to directly
— it only shares a JWT secret with it.
"""

from __future__ import annotations

from dependency_injector import providers

from genql.composition.eval_container import EvalContainer
from genql.infrastructure.auth.gotrue_jwt_verifier import GoTrueJwtVerifier
from genql.repositories.auth.sqlalchemy_user_profile_repository import (
    SqlAlchemyUserProfileRepository,
)
from genql.repositories.query.sqlalchemy_thread_repository import SqlAlchemyThreadRepository
from genql.repositories.query.sqlalchemy_turn_record_repository import (
    SqlAlchemyTurnRecordRepository,
)
from genql.services.auth.profile_service import ProfileService
from genql.services.query.thread_service import ThreadService


class AuthContainer(EvalContainer):
    token_verifier = providers.Singleton(
        GoTrueJwtVerifier, secret=EvalContainer.settings.provided.gotrue_jwt_secret
    )

    thread_repository = providers.Singleton(
        SqlAlchemyThreadRepository, engine=EvalContainer.semantic_engine
    )
    turn_record_repository = providers.Singleton(
        SqlAlchemyTurnRecordRepository, engine=EvalContainer.semantic_engine
    )
    user_profile_repository = providers.Singleton(
        SqlAlchemyUserProfileRepository, engine=EvalContainer.semantic_engine
    )

    thread_service = providers.Singleton(
        ThreadService,
        threads=thread_repository,
        turns=turn_record_repository,
    )
    profile_service = providers.Singleton(ProfileService, profiles=user_profile_repository)
