from aiogram.fsm.state import StatesGroup, State

class AddAccountState(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

class SetSettingState(StatesGroup):
    waiting_value = State()

class AddChannelState(StatesGroup):
    waiting_chat_id = State()
    waiting_type = State()

class LoadJsonState(StatesGroup):
    waiting_file = State()

class GetDiscussionIdState(StatesGroup):
    waiting_chat_id = State()