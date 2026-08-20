"""Channel OTP simulasi — mencatat ke log & mengungkap kode (mode dev/simulasi)."""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from .base import OTPChannel

logger = logging.getLogger("esign.otp")


class SimulatedOTPChannel(OTPChannel):
    name = "simulated"

    async def send(self, to: str, code: str, purpose: str = "",
                   meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info("[OTP:SIMULATED] to=%s purpose=%s code=%s", to or "-", purpose, code)
        return {
            "channel": self.name,
            "simulated": True,
            "to": to or "",
            "reveal_code": code,  # hanya untuk mode simulasi
            "message": f"OTP simulasi dibuat untuk {to or 'penandatangan'} (kode ditampilkan di layar).",
        }
