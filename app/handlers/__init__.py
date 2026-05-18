from aiogram import Dispatcher

from .admin import register_admin_handlers
from .client import register_client_handlers
from .common import register_common_handlers


def register_handlers(dp: Dispatcher) -> None:
    register_common_handlers(dp)
    register_admin_handlers(dp)
    register_client_handlers(dp)