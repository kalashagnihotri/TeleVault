from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import aiohttp

@dataclass(frozen=True, slots=True)
class TelegramResult:
    message_id: int
    raw: dict

class TelegramClient:
    def __init__(self, token: str, api_base_url: str) -> None:
        if not token:
            raise ValueError("Telegram token is required")
        self.token = token
        self.api_base_url = api_base_url
        self.base = f"{api_base_url.rstrip('/')}/bot{token}"

    async def send_photo_preview(
        self,
        *,
        chat_id: int,
        topic_id: int,
        photo_path: Path,
        caption: str,
    ) -> TelegramResult:
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        if topic_id > 0:
            form.add_field("message_thread_id", str(topic_id))
        form.add_field("caption", caption)
        form.add_field(
            "photo",
            photo_path.open("rb"),
            filename=photo_path.name,
            content_type="application/octet-stream",
        )
        result = await self._post("sendPhoto", form)
        if topic_id > 0 and "message_thread_id" in result.raw:
            if result.raw["message_thread_id"] != topic_id:
                raise ValueError(f"Response message_thread_id {result.raw['message_thread_id']} doesn't match requested {topic_id}")
        return result

    async def send_original_document(
        self,
        *,
        chat_id: int,
        topic_id: int,
        original_path: Path,
        reply_to_message_id: int | None = None,
        caption: str | None = None,
    ) -> TelegramResult:
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        if topic_id > 0:
            form.add_field("message_thread_id", str(topic_id))
        if reply_to_message_id is not None and reply_to_message_id > 0:
            form.add_field("reply_to_message_id", str(reply_to_message_id))
        if caption is not None:
            form.add_field("caption", caption)
        form.add_field(
            "document",
            original_path.open("rb"),
            filename=original_path.name,
            content_type="application/octet-stream",
        )
        result = await self._post("sendDocument", form)
        if topic_id > 0 and "message_thread_id" in result.raw:
            if result.raw["message_thread_id"] != topic_id:
                raise ValueError(f"Response message_thread_id {result.raw['message_thread_id']} doesn't match requested {topic_id}")
        return result

    async def download_file(self, file_id: str, destination_path: Path) -> Path:
        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. Get file path from Telegram
            async with session.get(f"{self.base}/getFile", params={"file_id": file_id}) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    desc = data.get("description", "Unknown error")
                    raise RuntimeError(f"Telegram getFile failed: {desc}")
                tg_file_path = data["result"]["file_path"]

            # 2. Download binary stream
            file_url = f"{self.api_base_url.rstrip('/')}/file/bot{self.token}/{tg_file_path}"
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Failed to download file from Telegram: HTTP {resp.status}")
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                with open(destination_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
        return destination_path

    async def _post(self, method: str, form: aiohttp.FormData) -> TelegramResult:
        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{self.base}/{method}", data=form) as response:
                try:
                    payload = await response.json(content_type=None)
                except Exception:
                    raise RuntimeError(f"Telegram returned non-JSON response. HTTP {response.status}")
                
                if response.status >= 400 or not payload.get("ok"):
                    error_code = payload.get("error_code", response.status)
                    description = payload.get("description", "Unknown error")
                    raise RuntimeError(f"Telegram API Error {error_code}: {description}")
                    
                result = payload["result"]
                msg_id = int(result["message_id"])
                
                if "chat" not in result or "id" not in result["chat"]:
                    raise ValueError("Payload missing chat ID")
                    
                if method == "sendPhoto":
                    if "photo" not in result or not result["photo"]:
                        raise ValueError("Payload missing photo object")
                elif method == "sendDocument":
                    if "document" not in result or "file_id" not in result["document"]:
                        raise ValueError("Payload missing document file_id")
                        
                return TelegramResult(message_id=msg_id, raw=result)
