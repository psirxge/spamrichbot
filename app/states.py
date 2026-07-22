from aiogram.fsm.state import StatesGroup, State

class AddAccountState(StatesGroup):
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

class AddParserAccountState(StatesGroup):
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

class SetSettingState(StatesGroup):
    waiting_value = State()

class AddChannelState(StatesGroup):
    waiting_chat_id = State()
    waiting_type = State()

class LoadSessionState(StatesGroup):
    waiting_file = State()
    waiting_api_id = State()
    waiting_api_hash = State()

class LoadJsonState(StatesGroup):
    waiting_file = State()