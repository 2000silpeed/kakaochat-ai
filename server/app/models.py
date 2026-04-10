from pydantic import BaseModel


class ChatMessage(BaseModel):
    room: str
    sender: str
    text: str
    ts: int  # unix timestamp (ms)
    is_group_chat: bool = True
    package_name: str = "com.kakao.talk"


class ServerStatus(BaseModel):
    status: str
    response_mode: str
    connected_clients: int
    total_messages_received: int
    digest_enabled: bool = False
