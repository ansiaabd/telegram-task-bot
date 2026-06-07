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


def user_picker_keyboard(users: list[dict], current_user_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("👤 Себя", callback_data="assignee_self")],
    ]
    for u in users:
        if u["user_id"] == current_user_id:
            continue
        label = u.get("full_name") or u.get("username") or f"ID {u['user_id']}"
        if u.get("username"):
            label += f" (@{u['username']})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"assignee_{u['user_id']}")])
    return InlineKeyboardMarkup(keyboard)
