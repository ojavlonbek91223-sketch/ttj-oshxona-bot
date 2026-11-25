"""Matn kiritish kutilayotgan holatlar (FSM)."""
from aiogram.fsm.state import State, StatesGroup


class PayStates(StatesGroup):
    amount = State()


class AddStates(StatesGroup):
    names = State()


class EditStates(StatesGroup):
    value = State()


class SearchStates(StatesGroup):
    query = State()


class FloorStates(StatesGroup):
    add = State()
    rename = State()


class ExpStates(StatesGroup):
    amount = State()
    desc = State()


class SetStates(StatesGroup):
    fee = State()
    fee_when = State()
    cash = State()
    admin = State()
