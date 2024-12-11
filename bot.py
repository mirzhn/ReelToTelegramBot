import logging
from logging.handlers import TimedRotatingFileHandler
from telegram.ext import ApplicationBuilder, MessageHandler, filters
from yt_dlp.utils import DownloadError
from yt_dlp import YoutubeDL
import re
import os
import configparser
import time
import threading

# Путь к конфигурационному файлу
CONFIG_FILE = "config.ini"

# Глобальный словарь для хранения настроек
config = {}

# Глобальные переменные для регулярных выражений
tiktok_regex = ''
instagram_regex = ''

def load_config():
    """Загружает конфигурацию из файла."""
    global config, tiktok_regex, instagram_regex
    parser = configparser.ConfigParser()
    parser.read(CONFIG_FILE)
    
    config = {
        "token": parser.get("General", "token", fallback=""),
        "log_level": parser.get("General", "log_level", fallback="INFO"),
        "downloads_dir": parser.get("Paths", "downloads_dir", fallback="downloads"),
        "logs_dir": parser.get("Paths", "logs_dir", fallback="logs"),
        "delete_old_files": parser.getboolean("Settings", "delete_old_files", fallback=True),
    }

    # Загрузка регулярных выражений для TikTok и Instagram
    tiktok_regex = parser.get("Regex", "tiktok_regex", fallback=r"(https?://)?(www\.)?(tiktok\.com/[\w\d\-]+|vm\.tiktok\.com/\w+)")
    instagram_regex = parser.get("Regex", "instagram_regex", fallback=r"(https?://)?(www\.)?instagram\.com/reel/[\w\d\-]+")

    # Создание директорий, если они не существуют
    os.makedirs(config["downloads_dir"], exist_ok=True)
    os.makedirs(config["logs_dir"], exist_ok=True)

def start_config_watcher(interval=60):
    """Фоновый процесс для регулярного перечитывания конфигурации."""
    def watcher():
        while True:
            load_config()
            time.sleep(interval)

    threading.Thread(target=watcher, daemon=True).start()

# Инициализация настроек
load_config()
start_config_watcher()

# Конфигурация логирования
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
app_log_handler = TimedRotatingFileHandler(f"{config['logs_dir']}/app.log", when="D", interval=1, backupCount=7)
app_log_handler.setFormatter(log_formatter)
app_log_handler.setLevel(logging.INFO)
error_log_handler = TimedRotatingFileHandler(f"{config['logs_dir']}/error.log", when="D", interval=1, backupCount=7)
error_log_handler.setFormatter(log_formatter)
error_log_handler.setLevel(logging.ERROR)

# Удаление логов HTTP-запросов от httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

logging.basicConfig(
    level=getattr(logging, config["log_level"].upper(), logging.INFO),
    handlers=[app_log_handler, error_log_handler, logging.StreamHandler()]
)

def download_video(url):
    """Скачивание видео по ссылке."""
    try:
        ydl_opts = {
            'format': 'mp4',
            'outtmpl': f"{config['downloads_dir']}/%(id)s.%(ext)s",
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return f"{config['downloads_dir']}/{info['id']}.mp4"
    except DownloadError as e:
        logging.error(f"Download error for URL {url}: {e}")
        raise

def delete_file(file_path):
    """Удаление файла."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"File {file_path} successfully deleted")
        else:
            logging.warning(f"File {file_path} does not exist")
    except Exception as e:
        logging.error(f"Error deleting file {file_path}: {e}")

async def handle_message(update, context):
    """Обработчик сообщений."""
    message = update.message
    chat_id = message.chat_id
    text = message.text
    reply_to_message_id = message.message_id

    try:
        if re.search(tiktok_regex, text) or re.search(instagram_regex, text):
            # Логирование подходящих сообщений
            logging.info(f"Valid message found in chat {chat_id}: '{text}'")

            url = re.search(tiktok_regex, text) or re.search(instagram_regex, text)
            video_path = download_video(url.group(0))
            with open(video_path, 'rb') as video:
                await context.bot.send_video(chat_id=chat_id, video=video, reply_to_message_id=reply_to_message_id)
                logging.info(f"Video successfully sent to chat {chat_id} in reply to message {reply_to_message_id}")
            if config["delete_old_files"]:
                delete_file(video_path)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        await update.message.reply_text("Oops, something gone wrong.")

def main():
    """Запуск бота."""
    application = ApplicationBuilder().token(config["token"]).build()
    text_handler = MessageHandler(filters.TEXT & filters.ChatType.GROUP, handle_message)
    application.add_handler(text_handler)
    logging.info("Bot started successfully")
    application.run_polling()

if __name__ == '__main__':
    main()
