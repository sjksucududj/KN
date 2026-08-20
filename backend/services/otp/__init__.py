"""Pluggable OTP channels untuk e-sign.

Default = 'simulated' (log + reveal kode, tanpa pengiriman nyata) sesuai pilihan
user (mode simulasi). Channel lain (whatsapp/email/sms) tinggal didaftarkan di
_CHANNELS tanpa mengubah pemanggil.
"""
from __future__ import annotations
import os
from typing import Dict, List, Type

from .base import OTPChannel
from .simulated import SimulatedOTPChannel

_CHANNELS: Dict[str, Type[OTPChannel]] = {
    "simulated": SimulatedOTPChannel,
    # "whatsapp": WhatsAppOTPChannel,  # future
    # "email": EmailOTPChannel,        # future
}


def get_otp_channel(name: str | None = None) -> OTPChannel:
    key = (name or os.environ.get("OTP_CHANNEL") or "simulated").lower()
    cls = _CHANNELS.get(key, SimulatedOTPChannel)
    return cls()


def available_channels() -> List[str]:
    return list(_CHANNELS.keys())
