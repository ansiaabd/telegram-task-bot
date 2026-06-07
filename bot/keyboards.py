from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def task_actions_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{task_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{task_id}"),
        ]
    ])


def approval_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{task_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{task_id}"),
        ]
    ])
