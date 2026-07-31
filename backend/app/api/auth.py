from fastapi import APIRouter, Cookie, Depends, HTTPException, Response

from app.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from app.config import Settings
from app.dependencies import get_current_user, get_user_repository
from app.repositories.user_repository import UserAlreadyExistsError, UserRepository
from app.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    PasswordChangeRequest,
    RegistrationRequest,
    StoredSessionUser,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=Settings().cookie_secure,
        path="/",
    )


async def create_session(response: Response, repository: UserRepository, user_id: int) -> None:
    token = new_session_token()
    await repository.create_session(user_id, hash_session_token(token))
    set_session_cookie(response, token)


def current_user_response(user: StoredSessionUser) -> CurrentUserResponse:
    return CurrentUserResponse(username=user.username, api_key_configured=bool(user.api_key.strip()))


@router.post("/register", status_code=201, response_model=CurrentUserResponse)
async def register(
    request: RegistrationRequest,
    response: Response,
    repository: UserRepository = Depends(get_user_repository),
) -> CurrentUserResponse:
    try:
        user = await repository.create(request.username, hash_password(request.password))
    except UserAlreadyExistsError:
        raise HTTPException(
            409,
            {"error": {"code": "username_taken", "message": "用户名已存在"}},
        ) from None
    await create_session(response, repository, user.id)
    return CurrentUserResponse(username=user.username, api_key_configured=False)


@router.post("/login", response_model=CurrentUserResponse)
async def login(
    request: LoginRequest,
    response: Response,
    repository: UserRepository = Depends(get_user_repository),
) -> CurrentUserResponse:
    user = await repository.get_by_username(request.username)
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            401,
            {"error": {"code": "invalid_credentials", "message": "用户名或密码错误"}},
        )
    await create_session(response, repository, user.id)
    return CurrentUserResponse(username=user.username, api_key_configured=bool(user.api_key.strip()))


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    repository: UserRepository = Depends(get_user_repository),
) -> None:
    if session_token:
        await repository.delete_session(hash_session_token(session_token))
    response.delete_cookie(key=SESSION_COOKIE, path="/")


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: StoredSessionUser = Depends(get_current_user)) -> CurrentUserResponse:
    return current_user_response(user)


@router.put("/password", status_code=204)
async def change_password(
    request: PasswordChangeRequest,
    response: Response,
    user: StoredSessionUser = Depends(get_current_user),
    repository: UserRepository = Depends(get_user_repository),
) -> None:
    stored_user = await repository.get_by_id(user.id)
    if stored_user is None or not verify_password(request.old_password, stored_user.password_hash):
        raise HTTPException(
            400,
            {"error": {"code": "invalid_old_password", "message": "旧密码错误"}},
        )
    await repository.update_password(user.id, hash_password(request.new_password))
    await repository.delete_sessions_for_user(user.id)
    response.delete_cookie(key=SESSION_COOKIE, path="/")
