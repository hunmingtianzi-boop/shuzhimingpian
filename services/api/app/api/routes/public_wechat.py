from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.api.errors import ApiError
from app.api.routes.wechat_auth import _rate_limit
from app.api.wechat_schemas import WeChatShareConfigEnvelope
from app.db.session import resolve_public_card_scope
from app.integrations.wechat import WeChatClient, WeChatConfigurationError, WeChatProviderError
from app.services.wechat_js_sdk import public_share_url, share_signature

router = APIRouter(tags=["Public WeChat"])


@router.get(
    "/public/cards/{slug}/wechat-js-sdk",
    response_model=WeChatShareConfigEnvelope,
    operation_id="getPublicCardWeChatJSSDKConfig",
)
async def config(
    slug: str,
    request: Request,
    response: Response,
    url: Annotated[str, Query(min_length=1, max_length=2_048)],
) -> WeChatShareConfigEnvelope:
    settings = request.app.state.settings
    signed_url = public_share_url(url, slug, settings)
    await _rate_limit(request)
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise ApiError(409, "WECHAT_NOT_CONFIGURED", "微信分享尚未配置，可复制链接分享")
    async with request.app.state.session_factory() as session, session.begin():
        scope = await resolve_public_card_scope(session, slug)
    if scope is None:
        raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
    try:
        ticket = await WeChatClient(
            settings=settings, http_client=request.app.state.http_client
        ).jsapi_ticket(getattr(request.app.state, "redis", None))
    except WeChatConfigurationError:
        raise ApiError(409, "WECHAT_NOT_CONFIGURED", "微信分享尚未配置，可复制链接分享") from None
    except WeChatProviderError as exc:
        raise ApiError(502, exc.code, "微信分享暂时不可用，可复制链接分享") from None
    response.headers["Cache-Control"] = "no-store"
    return WeChatShareConfigEnvelope(
        data=share_signature(
            app_id=settings.wechat_app_id,
            ticket=ticket,
            url=signed_url,
        )
    )
