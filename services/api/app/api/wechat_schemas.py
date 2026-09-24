from pydantic import Field

from app.api.auth_schemas import StaffTokenData, StrictAuthModel


class WeChatOAuthExchange(StrictAuthModel):
    code: str = Field(min_length=1, max_length=512)
    state: str = Field(pattern=r"^[0-9a-f]{64}$")


class WeChatLoginUrl(StrictAuthModel):
    authorize_url: str
    expires_in: int = 600


class WeChatLoginUrlEnvelope(StrictAuthModel):
    data: WeChatLoginUrl


class WeChatTokenData(StaffTokenData):
    return_to: str


class WeChatLoginEnvelope(StrictAuthModel):
    data: WeChatTokenData


class WeChatAvailability(StrictAuthModel):
    enabled: bool


class WeChatAvailabilityEnvelope(StrictAuthModel):
    data: WeChatAvailability


class WeChatShareConfig(StrictAuthModel):
    app_id: str
    timestamp: int
    nonce_str: str
    signature: str


class WeChatShareConfigEnvelope(StrictAuthModel):
    data: WeChatShareConfig
