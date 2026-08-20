"""Abstraksi OTP channel."""
from __future__ import annotations
from typing import Any, Dict, Optional


class OTPChannel:
    name: str = "base"

    async def send(self, to: str, code: str, purpose: str = "",
                   meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Kirim OTP. Return dict info pengiriman.

        Untuk channel simulasi, sertakan 'reveal_code' agar alur bisa selesai
        tanpa pengiriman nyata.
        """
        raise NotImplementedError
