"""Telegram Bot — 信号推送 + 交互式按钮（确认/跳过）"""

import logging
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from api.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger("telegram_bot")

# 全局 Bot 实例
_app: Application | None = None


def _format_signal(signal: dict) -> str:
    """格式化信号消息"""
    direction_emoji = "🟢" if signal["direction"] == "long" else "🔴"
    strength_stars = "⭐" * signal.get("strength", 1)

    lines = [
        f"{direction_emoji} **{signal['inst_id']}** {signal['bar']}",
        f"方向: **{signal['direction'].upper()}** {strength_stars}",
        f"入场价: `{signal['entry_price']:.2f}`",
        f"止损价: `{signal['stop_loss']:.2f}`",
    ]

    # 策略列表
    strategies = signal.get("strategies", [])
    if strategies:
        lines.append(f"策略: {', '.join(strategies)}")

    tag = signal.get("enter_tag", "")
    if tag:
        lines.append(f"标签: `{tag}`")

    return "\n".join(lines)


async def send_signal(signal: dict):
    """推送信号到 Telegram，附带确认/跳过按钮"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram 未配置，跳过推送")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    text = _format_signal(signal)
    signal_id = signal.get("id", 0)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 确认下单", callback_data=f"confirm:{signal_id}"),
            InlineKeyboardButton("⏭ 跳过", callback_data=f"skip:{signal_id}"),
        ]
    ])

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        logger.info(f"Telegram 推送成功: signal_id={signal_id}")
    except Exception as e:
        logger.error(f"Telegram 推送失败: {e}")


async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调：确认下单 / 跳过（仅授权用户）"""
    query = update.callback_query

    # 身份验证：只有 TELEGRAM_CHAT_ID 指定的用户可以操作
    if str(update.effective_user.id) != TELEGRAM_CHAT_ID:
        await query.answer("无权操作", show_alert=True)
        return

    await query.answer()

    data = query.data
    action, signal_id_str = data.split(":", 1)
    signal_id = int(signal_id_str)

    from api.database import get_db
    db = await get_db()

    if action == "confirm":
        await db.update_signal_status(signal_id, "confirmed")
        await query.edit_message_text(
            text=query.message.text + "\n\n⏳ **下单中...**",
            parse_mode="Markdown",
        )

        # 执行 OKX 下单
        from api.exchange.order_manager import execute_signal
        from api.exchange.okx_client import is_simulated
        try:
            result = await execute_signal(signal_id=signal_id)
            if result.get("success"):
                mode = result.get("mode", "模拟盘")
                await query.edit_message_text(
                    text=query.message.text +
                    f"\n\n✅ **[{mode}] 下单成功**\n"
                    f"金额: `{result['size_usdt']:.2f}` USDT\n"
                    f"张数: `{result['contract_size']}`\n"
                    f"成交价: `{result['price']:.2f}`",
                    parse_mode="Markdown",
                )
            else:
                await query.edit_message_text(
                    text=query.message.text +
                    f"\n\n❌ **下单失败**: {result.get('error', '未知错误')}",
                    parse_mode="Markdown",
                )
        except Exception as e:
            await query.edit_message_text(
                text=query.message.text + f"\n\n❌ **下单异常**: {e}",
                parse_mode="Markdown",
            )
        logger.info(f"Telegram 确认下单: signal_id={signal_id}")
    elif action == "skip":
        await db.update_signal_status(signal_id, "skipped")
        await query.edit_message_text(
            text=query.message.text + "\n\n⏭ **已跳过**",
            parse_mode="Markdown",
        )
        logger.info(f"Telegram 跳过信号: signal_id={signal_id}")


async def start_bot():
    """启动 Telegram Bot（polling 模式）"""
    global _app
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN in ("", "your_bot_token"):
        logger.info("Telegram Bot Token 未配置，跳过启动")
        return

    _app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    _app.add_handler(CallbackQueryHandler(_handle_callback))

    # 初始化 bot（不阻塞，使用 polling）
    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram Bot 已启动")


async def stop_bot():
    """停止 Telegram Bot"""
    global _app
    if _app:
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
        _app = None
        logger.info("Telegram Bot 已停止")
