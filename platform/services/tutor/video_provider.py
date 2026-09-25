import os

import httpx


class CloudflareStream:
    def __init__(self) -> None:
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.customer_code = os.getenv("CLOUDFLARE_CUSTOMER_CODE")

    @property
    def configured(self) -> bool:
        return bool(self.account_id and self.api_token)

    def create_upload(self, max_duration_seconds: int = 3600) -> dict:
        if not self.configured:
            raise RuntimeError("Cloudflare Stream is not configured")
        response = httpx.post(
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/stream/direct_upload",
            headers={"Authorization": f"Bearer {self.api_token}"},
            json={"maxDurationSeconds": max_duration_seconds},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError("Cloudflare Stream rejected the upload ticket")
        return payload["result"]

    def playback_url(self, provider_video_id: str) -> str:
        host = self.customer_code or "iframe.videodelivery.net"
        if self.customer_code:
            return f"https://{host}/{provider_video_id}/manifest/video.m3u8"
        return f"https://{host}/{provider_video_id}"