# FILE: modules/reminder/actions/jobs.py (FULLY REWRITTEN FOR MULTI-PANEL)

import datetime
import logging
import jdatetime
from telegram.ext import ContextTypes, Application
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio

# Use the correct, panel-aware functions and helpers
from shared import panel_utils
from database.crud import panel_credential as crud_panel
from modules.marzban.actions.constants import GB_IN_BYTES
from shared.log_channel import send_log
from database.crud import (
    bot_setting as crud_bot_setting,
    non_renewal_user as crud_non_renewal,
    pending_invoice as crud_invoice,
    bot_managed_user as crud_managed_user,
    user_note as crud_user_note,
    user as crud_user,
    marzban_link as crud_marzban_link
)
from modules.marzban.actions.data_manager import cleanup_marzban_user_data, normalize_username
from modules.payment.actions.approval import approve_payment

LOGGER = logging.getLogger(__name__)


async def _perform_auto_renewal(context: ContextTypes.DEFAULT_TYPE, telegram_user_id: int, marzban_username: str, subscription_price: int, api) -> bool:
    from shared.translator import translator
    price = float(subscription_price)
    new_balance = await crud_user.decrease_wallet_balance(telegram_user_id, price)
    if new_balance is None:
        LOGGER.error(f"Auto-renew for {marzban_username} aborted: Insufficient funds.")
        return False

    note_data = await crud_user_note.get_user_note(marzban_username)
    duration = note_data.subscription_duration if note_data else 30
    user_panel_data = await api.get_user_data(marzban_username)
    if not user_panel_data:
        LOGGER.error(f"Auto-renew for {marzban_username} failed: Could not get user data from panel.")
        await crud_user.increase_wallet_balance(telegram_user_id, price)
        return False
        
    volume_gb = (user_panel_data.get('data_limit', 0) / GB_IN_BYTES)
    plan_details = {
        'username': marzban_username, 'volume': volume_gb, 'duration': duration,
        'price': price, 'invoice_type': 'RENEWAL'
    }
    invoice_obj = await crud_invoice.create_pending_invoice({
        'user_id': telegram_user_id, 'plan_details': plan_details, 'price': int(price)
    })
    if not invoice_obj:
        LOGGER.critical(f"CRITICAL: Wallet balance for {marzban_username} was deducted, but invoice creation failed. Rolling back.")
        await crud_user.increase_wallet_balance(telegram_user_id, price)
        return False
    
    class MockUpdate:
        effective_user = type('obj', (object,), {'id': 0, 'full_name': "سیستم تمدید خودکار"})()
        callback_query = type('obj', (object,), {
            'data': f"approve_receipt_{invoice_obj.invoice_id}",
            'message': type('obj', (object,), {'caption': f"Auto-approved invoice #{invoice_obj.invoice_id}"})(),
            'answer': asyncio.coroutine(lambda *a, **kw: None),
            'edit_message_caption': asyncio.coroutine(lambda *a, **kw: None)
        })()
    try:
        await approve_payment(MockUpdate(), context)
        LOGGER.info(f"Auto-renewal for {marzban_username} (Invoice #{invoice_obj.invoice_id}) completed successfully.")
        return True
    except Exception as e:
        LOGGER.critical(f"CRITICAL: Auto-renewal for {marzban_username} failed at approval stage. Rolling back. Error: {e}", exc_info=True)
        await crud_user.increase_wallet_balance(telegram_user_id, price)
        return False


async def check_users_for_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import translator
    
    admin_id = context.job.chat_id
    bot_username = context.bot.username
    LOGGER.info(f"Executing daily multi-panel job for admin {admin_id}...")

    try:
        expired_count = await crud_invoice.expire_old_pending_invoices()
        if expired_count > 0:
            log_message = translator.get("reminder_jobs.invoice_expiry_report_title") + \
                          translator.get("reminder_jobs.invoice_expiry_report_body", count=f"`{expired_count}`")
            await send_log(context.bot, log_message, parse_mode=ParseMode.MARKDOWN)

        settings = await crud_bot_setting.load_bot_settings()
        days_threshold = settings.get('reminder_days', 3)
        data_gb_threshold = settings.get('reminder_data_gb', 1)
        non_renewal_list = await crud_non_renewal.get_all_non_renewal_users()
        
        all_links = await crud_marzban_link.get_all_marzban_links_with_panel()
        username_to_link_map = {link.marzban_username: link for link in all_links}
        
        all_panels = await crud_panel.get_all_panels()
        if not all_panels:
            await context.bot.send_message(admin_id, translator.get("reminder_jobs.daily_report_panel_error"))
            return

    except Exception as e:
        LOGGER.error(f"Critical error during pre-job preparation: {e}", exc_info=True)
        await context.bot.send_message(admin_id, "خطا در آماده‌سازی اولیه جاب روزانه.")
        return

    total_expiring, total_low_data, total_success_renew, total_fail_renew = [], [], [], []

    for panel in all_panels:
        LOGGER.info(f"--- Processing panel: {panel.name} (ID: {panel.id}) ---")
        api = await panel_utils._get_api_for_panel(panel)
        if not api:
            LOGGER.error(f"Could not create API for panel {panel.name}. Skipping.")
            continue

        panel_users = await api.get_all_users()
        if panel_users is None:
            LOGGER.error(f"Failed to fetch users from panel {panel.name}. Skipping.")
            continue
        
        panel_users_dict = {user['username']: user for user in panel_users if user.get('username')}
        
        processed_users_in_panel = set()

        auto_renew_links_for_this_panel = [link for link in all_links if link.panel_id == panel.id and link.auto_renew]
        
        for link in auto_renew_links_for_this_panel:
            marzban_username = link.marzban_username
            telegram_user_id = link.telegram_user_id
            
            panel_user = panel_users_dict.get(marzban_username)
            note_info = await crud_user_note.get_user_note(marzban_username)
            
            if not panel_user or panel_user.get('status') != 'active' or (note_info and note_info.is_test_account):
                continue

            if expire_ts := panel_user.get('expire'):
                expire_date = datetime.datetime.fromtimestamp(expire_ts)
                now = datetime.datetime.now()
                if now < expire_date < (now + datetime.timedelta(days=days_threshold)):
                    wallet_balance = await crud_user.get_user_wallet_balance(telegram_user_id) or 0.0
                    price = float(note_info.subscription_price) if note_info and note_info.subscription_price else 0.0

                    if wallet_balance >= price and price > 0:
                        full_user_data = {
                            "telegram_user_id": telegram_user_id, "marzban_username": marzban_username,
                            "subscription_price": int(price), "api": api
                        }
                        if await _perform_auto_renewal(context, **full_user_data):
                            panel_user['panel_name'] = panel.name
                            total_success_renew.append(panel_user)
                        else:
                            panel_user['panel_name'] = panel.name
                            total_fail_renew.append(panel_user)
                    else:
                        try:
                            await context.bot.send_message(telegram_user_id, translator.get("reminder_jobs.auto_renew_failed_customer_funds"))
                            panel_user['panel_name'] = panel.name
                            total_fail_renew.append(panel_user)
                        except Exception as e:
                            LOGGER.warning(f"Failed to send warning to customer for {marzban_username}: {e}")
                    
                    processed_users_in_panel.add(marzban_username)
        
        for panel_user in panel_users:
            username = panel_user.get('username')
            if not username or username in processed_users_in_panel or username in non_renewal_list:
                continue

            note_info = await crud_user_note.get_user_note(username)
            if panel_user.get('status') != 'active' or (note_info and note_info.is_test_account):
                continue

            is_expiring, is_low_data, expire_date = False, False, None
            if expire_ts := panel_user.get('expire'):
                expire_date = datetime.datetime.fromtimestamp(expire_ts)
                if datetime.datetime.now() < expire_date < (datetime.datetime.now() + datetime.timedelta(days=days_threshold)):
                    is_expiring = True
            
            data_limit = panel_user.get('data_limit') or 0
            if data_limit > 0 and (data_limit - (panel_user.get('used_traffic') or 0)) < (data_gb_threshold * GB_IN_BYTES):
                is_low_data = True
            
            user_link = username_to_link_map.get(username)
            if user_link and (is_expiring or is_low_data):
                try:
                    customer_message = translator.get("reminder_jobs.customer_reminder_title", username=f"`{username}`")
                    if is_expiring and expire_date:
                        time_left = expire_date - datetime.datetime.now()
                        customer_message += translator.get("reminder_jobs.customer_reminder_days_left", days=time_left.days + 1)
                    if is_low_data:
                        remaining_gb = (data_limit - (panel_user.get('used_traffic') or 0)) / GB_IN_BYTES
                        customer_message += translator.get("reminder_jobs.customer_reminder_data_left", gb=f"{remaining_gb:.2f}")
                    customer_message += translator.get("reminder_jobs.customer_reminder_footer")
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton(translator.get("reminder_jobs.button_request_renewal"), callback_data=f"customer_renew_request_{username}"),
                        InlineKeyboardButton(translator.get("reminder_jobs.button_do_not_renew"), callback_data=f"customer_do_not_renew_{username}")]])
                    await context.bot.send_message(chat_id=user_link.telegram_user_id, text=customer_message, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
                except Exception as e:
                    LOGGER.warning(f"Failed to send reminder to customer {user_link.telegram_user_id} for user {username}: {e}")

            if is_expiring:
                panel_user['panel_name'] = panel.name
                total_expiring.append(panel_user)
            if is_low_data and not is_expiring:
                panel_user['panel_name'] = panel.name
                total_low_data.append(panel_user)

    if any([total_expiring, total_low_data, total_success_renew, total_fail_renew]):
        jalali_today = jdatetime.datetime.now().strftime('%Y/%m/%d')
        report_parts = [translator.get("reminder_jobs.admin_daily_report_title", date=jalali_today)]
        
        def format_user_line(u, reason):
            uname = u.get('username', 'N/A')
            pname = u.get('panel_name', '??')
            return f"▪️ <a href='https://t.me/{bot_username}?start=details_{uname}'>{uname}</a> ({pname}) - <i>{reason}</i>"

        if total_success_renew:
            report_parts.append("\n✅ **تمدیدهای خودکار موفق**")
            for u in total_success_renew: report_parts.append(format_user_line(u, "موفقیت‌آمیز"))
        if total_fail_renew:
            report_parts.append("\n⚠️ **تمدیدهای خودکار ناموفق**")
            for u in total_fail_renew: report_parts.append(format_user_line(u, "ناموفق (موجودی ناکافی)"))
        if total_expiring:
            report_parts.append(translator.get("reminder_jobs.admin_report_expiring_users_title"))
            for u in total_expiring:
                time_left = datetime.datetime.fromtimestamp(u['expire']) - datetime.datetime.now()
                reason = translator.get("reminder_jobs.admin_report_expiring_reason", days=time_left.days + 1)
                report_parts.append(format_user_line(u, reason))
        if total_low_data:
            report_parts.append(translator.get("reminder_jobs.admin_report_low_data_users_title"))
            for u in total_low_data:
                rem_gb = ((u.get('data_limit', 0)) - (u.get('used_traffic', 0))) / GB_IN_BYTES
                reason = translator.get("reminder_jobs.admin_report_low_data_reason", gb=f"{rem_gb:.1f}")
                report_parts.append(format_user_line(u, reason))
                
        await context.bot.send_message(admin_id, "\n".join(report_parts), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    else:
        LOGGER.info("No items to report today across all panels. Reminder job finished.")
    
    await auto_delete_expired_users(context)


async def auto_delete_expired_users(context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import translator
    LOGGER.info("Starting multi-panel auto-delete job for expired users...")
    
    settings = await crud_bot_setting.load_bot_settings()
    grace_days = settings.get('auto_delete_grace_days', 0)
    if grace_days <= 0:
        LOGGER.info("Auto-delete is disabled. Skipping."); return

    managed_users_set = set(await crud_managed_user.get_all_managed_users())
    if not managed_users_set:
        LOGGER.info("No bot-managed users found. Auto-delete job finished."); return
    
    all_panels = await crud_panel.get_all_panels()
    if not all_panels:
        LOGGER.warning("Auto-delete job failed: No panels configured."); return

    total_deleted_users = []
    grace_period = datetime.timedelta(days=grace_days)

    for panel in all_panels:
        LOGGER.info(f"--- [Auto-Delete] Checking panel: {panel.name} ---")
        api = await panel_utils._get_api_for_panel(panel)
        if not api: continue

        panel_users = await api.get_all_users()
        if panel_users is None: continue

        for user in panel_users:
            username = user.get('username')
            if not username or user.get('status') == 'active' or username not in managed_users_set:
                continue
                
            if expire_ts := user.get('expire'):
                expire_date = datetime.datetime.fromtimestamp(expire_ts)
                if datetime.datetime.now() > (expire_date + grace_period):
                    LOGGER.info(f"User '{username}' on panel '{panel.name}' is expired for more than {grace_days} days. Deleting...")
                    success, _ = await api.delete_user(username)
                    if success:
                        await cleanup_marzban_user_data(username)
                        total_deleted_users.append(f"{username} ({panel.name})")
                    else:
                        LOGGER.error(f"Failed to delete user '{username}' from panel '{panel.name}'.")
    
    if total_deleted_users:
        safe_deleted_list = ", ".join(f"`{u}`" for u in total_deleted_users)
        log_message = translator.get("reminder_jobs.auto_delete_report_title") + \
                      translator.get("reminder_jobs.auto_delete_report_body", count=len(total_deleted_users), users=safe_deleted_list)
        await send_log(context.bot, log_message, parse_mode=ParseMode.MARKDOWN)
    else:
        LOGGER.info("Auto-delete job finished. No users met deletion criteria across all panels.")


async def cleanup_expired_test_accounts(context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import translator
    LOGGER.info("Starting multi-panel cleanup for expired test accounts...")
    
    test_accounts = await crud_user_note.get_all_test_accounts()
    if not test_accounts:
        LOGGER.info("Test account cleanup finished. No test accounts in DB."); return
        
    all_panels = await crud_panel.get_all_panels()
    if not all_panels:
        LOGGER.warning("Test account cleanup failed: No panels configured."); return

    deleted_users_count = 0
    all_links = await crud_marzban_link.get_all_marzban_links_with_panel()
    username_to_link_map = {link.marzban_username: link for link in all_links}

    # Create a map for quick API object retrieval
    panel_apis = {panel.id: await panel_utils._get_api_for_panel(panel) for panel in all_panels}

    for test_account in test_accounts:
        username = test_account.username
        link = username_to_link_map.get(username)
        if not link or not link.panel_id:
            LOGGER.warning(f"Test account '{username}' has no panel link in DB. Cleaning up DB records.")
            await cleanup_marzban_user_data(username)
            continue
        
        api = panel_apis.get(link.panel_id)
        if not api:
            LOGGER.error(f"Could not get API for panel ID {link.panel_id} for test user '{username}'.")
            continue

        user_data = await api.get_user_data(username)
        
        if not user_data:
            LOGGER.warning(f"Test account '{username}' found in DB but not on panel '{link.panel.name}'. Cleaning up DB records.")
            await cleanup_marzban_user_data(username)
            continue
            
        if expire_ts := user_data.get('expire', 0):
            if expire_ts < datetime.datetime.now().timestamp():
                LOGGER.info(f"Test account '{username}' on panel '{link.panel.name}' has expired. Deleting...")
                success, message = await api.delete_user(username)
                if success:
                    await cleanup_marzban_user_data(username)
                    deleted_users_count += 1
                    LOGGER.info(f"Successfully deleted expired test account '{username}'.")
                else:
                    LOGGER.error(f"Failed to delete expired test account '{username}'. API Error: {message}")
    
    if deleted_users_count > 0:
        log_message = translator.get("reminder_jobs.test_account_cleanup_report", count=deleted_users_count)
        await send_log(context.bot, log_message)
    else:
        LOGGER.info("Test account cleanup finished. No accounts were expired.")


# --- Scheduling functions remain the same ---
async def schedule_initial_daily_job(application: Application):
    try:
        settings = await crud_bot_setting.load_bot_settings()
        admin_id = application.bot_data.get('admin_id_for_jobs')
        if not admin_id: LOGGER.warning("Cannot schedule daily job: Admin ID not found."); return
        time_obj = datetime.datetime.strptime(settings.get('reminder_time', "09:00"), '%H:%M').time()
        await schedule_daily_job(application, time_obj)
    except Exception as e:
        LOGGER.error(f"Failed to schedule initial daily job: {e}", exc_info=True)

async def schedule_daily_job(application: Application, time_obj: datetime.time):
    admin_id = application.bot_data.get('admin_id_for_jobs')
    if not admin_id: return
    
    job_queue = application.job_queue
    if not job_queue: LOGGER.warning("JobQueue is not available."); return
        
    job_name = f"daily_reminder_job_{admin_id}"
    for job in job_queue.get_jobs_by_name(job_name): job.schedule_removal()

    tehran_tz = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
    job_time = datetime.time(hour=time_obj.hour, minute=time_obj.minute, tzinfo=tehran_tz)
    
    job_queue.run_daily(callback=check_users_for_reminders, time=job_time, chat_id=admin_id, name=job_name)
    LOGGER.info(f"Daily job (reminders & cleanup) scheduled for {job_time.strftime('%H:%M')} Tehran time.")