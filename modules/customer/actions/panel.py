# FILE: modules/customer/actions/panel.py (NAMESPACE CORRECTED)

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from shared.keyboards import get_customer_shop_keyboard
from shared.translator import _

async def show_customer_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Displays the main customer shop menu using a ReplyKeyboardMarkup.
    (MODIFIED to handle both Message and CallbackQuery)
    """
    reply_markup = await get_customer_shop_keyboard()
    text = _("customer.customer_panel.shop_welcome")
    
    chat_id = update.effective_chat.id
    target_message = update.callback_query.message if update.callback_query else update.message

    if update.callback_query:
        await update.callback_query.answer()
        # Delete the broadcast message and send the shop menu as a new message
        await target_message.delete()
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await target_message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )