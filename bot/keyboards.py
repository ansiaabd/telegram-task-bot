from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def task_actions_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{task_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{task_id}"),
        ]
    ])
