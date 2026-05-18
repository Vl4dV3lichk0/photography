from aiogram.fsm.state import State, StatesGroup


class AdminAddCityState(StatesGroup):
    waiting_city_name = State()


class AdminWorkingWindowState(StatesGroup):
    waiting_city = State()
    waiting_date = State()
    waiting_hours = State()


class AdminBlockState(StatesGroup):
    waiting_city = State()
    waiting_date = State()
    waiting_hours = State()
    waiting_reason = State()


class AdminPriceState(StatesGroup):
    waiting_hour_price = State()


class AdminArchiveState(StatesGroup):
    waiting_delete_confirmation = State()


class ClientBookingState(StatesGroup):
    waiting_city = State()
    waiting_month = State()
    waiting_day = State()
    waiting_hours = State()
    waiting_contact = State()
    waiting_name = State()
    waiting_phone = State()
    waiting_shoot_type = State()
    waiting_comment = State()
    waiting_consent = State()