from fastapi import APIRouter, Cookie, Depends, HTTPException, Response

from app.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    hash_password,
    hash_session_token,
    new_session_token,
    new_verification_code,
    verify_password,
)
from app.config import Settings
from app.dependencies import (
    get_current_user,
    get_email_sender,
    get_user_repository,
    get_verification_code_repository,
)
from app.repositories.user_repository import (
    EmailAlreadyExistsError,
    UserAlreadyExistsError,
    UserRepository,
)
from app.repositories.verification_code_repository import (
    VerificationCodeCooldownError,
    VerificationCodeRepository,
)
from app.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    PasswordChangeRequest,
    RegistrationRequest,
    StoredSessionUser,
    VerificationCodeRequest,
    VerificationCodeResponse,
)
from app.services.email_sender import (
    EmailDeliveryError,
    EmailSender,
    EmailSenderNotConfiguredError,
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
    return CurrentUserResponse(
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        api_key_configured=bool(user.api_key.strip()),
    )


def configured_admin_emails() -> set[str]:
    return Settings().admin_email_set


@router.post("/verification-code", response_model=VerificationCodeResponse)
async def send_verification_code(
    request: VerificationCodeRequest,
    repository: UserRepository = Depends(get_user_repository),
    code_repository: VerificationCodeRepository = Depends(get_verification_code_repository),
    sender: EmailSender = Depends(get_email_sender),
) -> VerificationCodeResponse:
    if await repository.get_by_email(request.email) is not None:
        raise HTTPException(
            409,
            {"error": {"code": "email_registered", "message": "该邮箱已注册"}},
        )
    settings = Settings()
    code = new_verification_code()
    try:
        await code_repository.store(
            request.email,
            hash_password(code),
            ttl_seconds=settings.verification_code_ttl_seconds,
            cooldown_seconds=settings.verification_code_cooldown_seconds,
        )
    except VerificationCodeCooldownError as exc:
        raise HTTPException(
            429,
            {
                "error": {
                    "code": "verification_code_cooldown",
                    "message": f"请在 {exc.retry_after_seconds} 秒后重试",
                    "retry_after_seconds": exc.retry_after_seconds,
                }
            },
        ) from None
    try:
        await sender.send_verification_code(request.email, code)
    except EmailSenderNotConfiguredError:
        await code_repository.delete(request.email)
        raise HTTPException(
            503,
            {"error": {"code": "smtp_not_configured", "message": "邮件服务尚未配置"}},
        ) from None
    except EmailDeliveryError:
        await code_repository.delete(request.email)
        raise HTTPException(
            502,
            {"error": {"code": "email_delivery_failed", "message": "验证码邮件发送失败"}},
        ) from None
    return VerificationCodeResponse(
        message="验证码已发送",
        retry_after_seconds=settings.verification_code_cooldown_seconds,
    )


@router.post("/register", status_code=201, response_model=CurrentUserResponse)
async def register(
    request: RegistrationRequest,
    response: Response,
    repository: UserRepository = Depends(get_user_repository),
    code_repository: VerificationCodeRepository = Depends(get_verification_code_repository),
) -> CurrentUserResponse:
    if not await code_repository.verify(request.email, request.verification_code):
        raise HTTPException(
            400,
            {"error": {"code": "invalid_verification_code", "message": "验证码错误或已失效"}},
        )
    is_admin = request.email in configured_admin_emails()
    legacy_user = await repository.get_by_username(request.username)
    try:
        if legacy_user is not None and legacy_user.email is None:
            if not verify_password(request.password, legacy_user.password_hash):
                raise HTTPException(
                    409,
                    {
                        "error": {
                            "code": "legacy_password_required",
                            "message": "旧账号需使用原密码绑定邮箱",
                        }
                    },
                )
            await repository.bind_verified_email(legacy_user.id, request.email, is_admin)
            user = await repository.get_by_id(legacy_user.id)
            if user is None:
                raise RuntimeError("Migrated user cannot be loaded")
        else:
            user = await repository.create(
                request.username,
                hash_password(request.password),
                email=request.email,
                is_admin=is_admin,
            )
    except EmailAlreadyExistsError:
        raise HTTPException(
            409,
            {"error": {"code": "email_registered", "message": "该邮箱已注册"}},
        ) from None
    except UserAlreadyExistsError:
        raise HTTPException(
            409,
            {"error": {"code": "username_taken", "message": "用户名已存在"}},
        ) from None
    await code_repository.delete(request.email)
    await create_session(response, repository, user.id)
    session_user = await repository.get_by_id(user.id)
    if session_user is None or session_user.email is None:
        raise RuntimeError("Created user cannot be loaded")
    return CurrentUserResponse(
        username=session_user.username,
        email=session_user.email,
        is_admin=session_user.is_admin,
        api_key_configured=False,
    )


@router.post("/login", response_model=CurrentUserResponse)
async def login(
    request: LoginRequest,
    response: Response,
    repository: UserRepository = Depends(get_user_repository),
) -> CurrentUserResponse:
    user = await repository.get_by_email(request.email)
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            401,
            {"error": {"code": "invalid_credentials", "message": "邮箱或密码错误"}},
        )
    should_be_admin = request.email in configured_admin_emails()
    if user.is_admin != should_be_admin:
        await repository.set_admin(user.id, should_be_admin)
    await create_session(response, repository, user.id)
    refreshed = await repository.get_by_id(user.id)
    if refreshed is None or refreshed.email is None:
        raise RuntimeError("Authenticated user cannot be loaded")
    return CurrentUserResponse(
        username=refreshed.username,
        email=refreshed.email,
        is_admin=refreshed.is_admin,
        api_key_configured=bool(refreshed.api_key.strip()),
    )


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
