import os
import tempfile
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import whisper
from pydub import AudioSegment
from pydub.utils import make_chunks
import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramTranscriberBot:
    def __init__(self, token: str):
        self.token = token
        self.model = None
        self.user_sessions = {}
        
    async def load_model(self):
        """Загрузка модели Whisper"""
        if self.model is None:
            logger.info("Загрузка модели Whisper...")
            self.model = whisper.load_model("base")
            logger.info("Модель загружена!")
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "Я бот для преобразования аудио в текст.\n\n"
            "📎 Просто отправь мне аудиофайл (MP3, WAV, M4A и др.) и я преобразую его в текст.\n\n"
            "⚡ Поддерживаю файлы до 4 часов!\n\n"
            "Используй /help для справки"
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
🎧 **Аудио в Текст Бот**

**Поддерживаемые форматы:**
• MP3, WAV, M4A, FLAC, OGG, WMA, AAC
• Максимальный размер: 50 МБ (ограничение Telegram)
• Максимальная длительность: 4 часа

**Как использовать:**
1. Просто отправь аудиофайл
2. Бот автоматически определит язык
3. Получишь текстовую расшифровку

**Команды:**
/start - начать работу
/help - эта справка
/status - статус обработки

**Примечание:** Обработка длинных файлов может занять несколько минут.
        """
        await update.message.reply_text(help_text)
    
    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка аудиофайлов"""
        user_id = update.effective_user.id
        
        try:
            # Получаем файл
            audio_file = await update.message.audio.get_file()
            file_name = update.message.audio.file_name or "audio_file"
            
            # Уведомляем пользователя
            status_msg = await update.message.reply_text(
                f"📥 Получен файл: {file_name}\n"
                f"⏳ Начинаю обработку..."
            )
            
            # Создаем временные файлы
            with tempfile.NamedTemporaryFile(delete=False, suffix='.audio') as temp_input:
                input_path = temp_input.name
            
            # Скачиваем файл
            await audio_file.download_to_drive(input_path)
            
            # Обрабатываем аудио
            result_text = await self.process_audio(input_path, user_id, status_msg)
            
            # Отправляем результат
            if len(result_text) > 4096:
                # Разбиваем длинный текст на части
                for i in range(0, len(result_text), 4096):
                    await update.message.reply_text(result_text[i:i+4096])
            else:
                await update.message.reply_text(f"📝 **Результат транскрипции:**\n\n{result_text}")
            
            # Удаляем временные файлы
            os.unlink(input_path)
            
        except Exception as e:
            logger.error(f"Ошибка обработки аудио: {e}")
            await update.message.reply_text(f"❌ Ошибка обработки: {str(e)}")
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка голосовых сообщений"""
        user_id = update.effective_user.id
        
        try:
            status_msg = await update.message.reply_text("🎤 Обрабатываю голосовое сообщение...")
            
            # Получаем голосовое сообщение
            voice_file = await update.message.voice.get_file()
            
            # Создаем временные файлы
            with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_input:
                input_path = temp_input.name
            
            # Скачиваем и конвертируем
            await voice_file.download_to_drive(input_path)
            
            # Конвертируем OGG в WAV
            audio = AudioSegment.from_ogg(input_path)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_wav:
                wav_path = temp_wav.name
                audio.export(wav_path, format="wav")
            
            # Обрабатываем
            result_text = await self.process_audio(wav_path, user_id, status_msg)
            
            await update.message.reply_text(f"🎤 **Расшифровка голосового сообщения:**\n\n{result_text}")
            
            # Очистка
            os.unlink(input_path)
            os.unlink(wav_path)
            
        except Exception as e:
            logger.error(f"Ошибка обработки голосового: {e}")
            await update.message.reply_text(f"❌ Ошибка обработки голосового: {str(e)}")
    
    async def process_audio(self, audio_path: str, user_id: int, status_msg):
        """Основная функция обработки аудио"""
        try:
            await self.load_model()
            
            # Загружаем аудио
            await status_msg.edit_text("🔄 Загружаю аудиофайл...")
            audio = AudioSegment.from_file(audio_path)
            duration_minutes = len(audio) / (1000 * 60)
            
            await status_msg.edit_text(f"📊 Длительность: {duration_minutes:.1f} минут\n⏳ Начинаю транскрипцию...")
            
            # Для длинных файлов разбиваем на части
            if duration_minutes > 30:
                return await self.process_long_audio(audio, duration_minutes, status_msg)
            else:
                return await self.process_short_audio(audio_path, status_msg)
                
        except Exception as e:
            raise e
    
    async def process_short_audio(self, audio_path: str, status_msg):
        """Обработка коротких аудио (до 30 минут)"""
        await status_msg.edit_text("🔊 Распознаю речь...")
        
        result = self.model.transcribe(audio_path, language=None, fp16=False)
        
        await status_msg.edit_text("✅ Обработка завершена!")
        return result["text"]
    
    async def process_long_audio(self, audio: AudioSegment, duration_minutes: float, status_msg):
        """Обработка длинных аудио (более 30 минут)"""
        chunk_length_minutes = 25  # 25 минут на часть
        chunk_length_ms = chunk_length_minutes * 60 * 1000
        
        chunks = make_chunks(audio, chunk_length_ms)
        total_chunks = len(chunks)
        
        await status_msg.edit_text(
            f"📁 Разбиваю на {total_chunks} частей по {chunk_length_minutes} минут\n"
            f"⏳ Обработка может занять несколько минут..."
        )
        
        full_text = ""
        temp_files = []
        
        try:
            for i, chunk in enumerate(chunks, 1):
                progress = (i / total_chunks) * 100
                await status_msg.edit_text(
                    f"⏳ Обработка части {i}/{total_chunks} ({progress:.1f}%)..."
                )
                
                # Сохраняем временный chunk
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                    chunk_path = temp_file.name
                    temp_files.append(chunk_path)
                
                chunk.export(chunk_path, format="wav")
                
                # Транскрибируем
                result = self.model.transcribe(chunk_path, language=None, fp16=False)
                
                # Добавляем временную метку
                start_time = (i-1) * chunk_length_minutes * 60
                time_str = self.format_time(start_time)
                
                full_text += f"\n--- Часть {i} [{time_str}] ---\n{result['text']}\n"
            
            await status_msg.edit_text("✅ Все части обработаны!")
            
        finally:
            # Очистка временных файлов
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except:
                    pass
        
        return full_text
    
    def format_time(self, seconds):
        """Форматирование времени"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Ошибка: {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка при обработке. Попробуйте позже."
            )
    
    def run(self):
        """Запуск бота"""
        application = Application.builder().token(self.token).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(MessageHandler(filters.AUDIO, self.handle_audio))
        application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        
        # Обработчик ошибок
        application.add_error_handler(self.error_handler)
        
        # Запуск
        logger.info("Бот запущен!")
        application.run_polling()

# Файл конфигурации
if __name__ == "__main__":
    # Получаем токен из переменных окружения
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not BOT_TOKEN:
        print("❌ Установите TELEGRAM_BOT_TOKEN в переменных окружения")
        exit(1)
    
    bot = TelegramTranscriberBot(BOT_TOKEN)
    bot.run()