#!/usr/bin/env python3
import os
from bot import TelegramTranscriberBot

if __name__ == "__main__":
    # Токен бота (лучше хранить в переменных окружения)
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not BOT_TOKEN:
        print("❌ Укажите TELEGRAM_BOT_TOKEN:")
        print("export TELEGRAM_BOT_TOKEN='your_bot_token_here'")
        exit(1)
    
    bot = TelegramTranscriberBot(BOT_TOKEN)
    bot.run()