import os
import logging
import asyncio
import threading
import http.server
import socketserver
from typing import Dict, List, Optional
import pandas as pd
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json
import openpyxl
from openpyxl import load_workbook
from io import BytesIO

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- start tiny health server (to satisfy Render's port check) ---
class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # only respond on root path; otherwise 404
        if self.path == '/' or self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # silence default logging or route to our logger
        logger.debug("%s - - %s" % (self.client_address[0], format%args))

def start_health_server():
    try:
        port = int(os.environ.get("PORT", 8000))
    except Exception:
        port = 8000
    server = socketserver.TCPServer(("", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health server started on port {port}")

# call this before initializing the bot
start_health_server()
# --- end health server ---

# Bot configuration
BOT_TOKEN = "8241417536:AAEz1MSmcbfR7BNlcZmi60p1LUJXBntZPC4"
LOCAL_EXCEL_FILE = "Расходники 9 октября.xlsx"
GOOGLE_SHEET_ID = "1McGe_kQVIonC4soSTi1nPjH4WlGI0vlS"  # Existing Google Sheet ID
GOOGLE_SHEET_NAME = "Inventory Bot Sheet"
GOOGLE_API_KEY = "AIzaSyDkcrwCG5UimwKx4oFdIXzjH_l8UaeOtX4"

# Google Sheets API scopes
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

class InventoryBot:
    def __init__(self):
        self.service = None
        self.drive_service = None
        self.inventory_data = None
        self.google_sheet_id = GOOGLE_SHEET_ID  # Use existing sheet ID
        self.user_states = {}  # Для отслеживания состояний пользователей
        self.setup_google_services()
        self.download_excel_from_google_drive()  # Download latest Excel from Google Drive on startup
    
    def setup_google_services(self):
        """Setup Google Sheets and Drive API connections"""
        try:
            # Check if service account JSON is provided as environment variable
            if os.getenv('SERVICE_ACCOUNT_JSON'):
                logger.info("Loading service account from environment variable")
                credentials_data = json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_data, scopes=SCOPES)
                self.service = build('sheets', 'v4', credentials=credentials)
                self.drive_service = build('drive', 'v3', credentials=credentials)
                logger.info("Google services initialized with environment variable")
            elif os.path.exists('service_account.json'):
                credentials = service_account.Credentials.from_service_account_file(
                    'service_account.json', scopes=SCOPES)
                self.service = build('sheets', 'v4', credentials=credentials)
                self.drive_service = build('drive', 'v3', credentials=credentials)
                logger.info("Google services initialized with service account file")
            else:
                logger.warning("No service account found. Google Sheets sync will be disabled.")
        except Exception as e:
            logger.error(f"Error setting up Google services: {e}")
    
    def load_local_inventory(self) -> pd.DataFrame:
        """Load inventory data from local Excel file"""
        try:
            if not os.path.exists(LOCAL_EXCEL_FILE):
                logger.error(f"Local Excel file '{LOCAL_EXCEL_FILE}' not found")
                return pd.DataFrame()
            
            # Load Excel file
            df = pd.read_excel(LOCAL_EXCEL_FILE)
            
            # Replace NaN values with 0 or empty string
            df = df.fillna(0)
            
            # For text columns, replace 0 with empty string
            for col in df.columns:
                if df[col].dtype == 'object':  # Text columns
                    df[col] = df[col].replace(0, '')
            
            self.inventory_data = df
            logger.info(f"Loaded {len(df)} instruments from local Excel file")
            return df
            
        except Exception as e:
            logger.error(f"Error loading local inventory: {e}")
            return pd.DataFrame()
    
    def create_or_update_google_sheet(self):
        """Create or update Google Sheet from local data"""
        if not self.service or self.inventory_data is None:
            logger.warning("Cannot create Google Sheet - missing service or data")
            return
        
        try:
            # Check if we already have a sheet ID stored
            if os.path.exists('google_sheet_id.txt'):
                with open('google_sheet_id.txt', 'r') as f:
                    self.google_sheet_id = f.read().strip()
                logger.info(f"Using existing Google Sheet: {self.google_sheet_id}")
                self.update_google_sheet()
            else:
                logger.info("Attempting to create new Google Sheet...")
                self.create_new_google_sheet()
                
        except Exception as e:
            logger.error(f"Error managing Google Sheet: {e}")
            logger.info("Bot will continue with local-only mode")
    
    def create_new_google_sheet(self):
        """Create a new Google Sheet"""
        try:
            # Create new spreadsheet
            spreadsheet_body = {
                'properties': {
                    'title': GOOGLE_SHEET_NAME
                }
            }
            
            spreadsheet = self.service.spreadsheets().create(
                body=spreadsheet_body,
                fields='spreadsheetId'
            ).execute()
            
            self.google_sheet_id = spreadsheet.get('spreadsheetId')
            
            # Save the sheet ID for future use
            with open('google_sheet_id.txt', 'w') as f:
                f.write(self.google_sheet_id)
            
            logger.info(f"Created new Google Sheet: {self.google_sheet_id}")
            
            # Upload data to the new sheet
            self.update_google_sheet()
            return True
            
        except Exception as e:
            logger.error(f"Error creating Google Sheet: {e}")
            return False
    
    def update_google_sheet(self):
        """Update Google Sheet by uploading the updated Excel file"""
        if not self.drive_service or not self.google_sheet_id or self.inventory_data is None:
            logger.warning("Google Drive service not available")
            return False
        
        try:
            # First, save the current data to local Excel file
            self.save_local_inventory()
            
            # Upload the updated Excel file to Google Drive
            file_metadata = {
                'name': LOCAL_EXCEL_FILE
            }
            
            media = MediaFileUpload(LOCAL_EXCEL_FILE, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            
            # Update the existing file in Google Drive
            self.drive_service.files().update(
                fileId=self.google_sheet_id,
                body=file_metadata,
                media_body=media
            ).execute()
            
            logger.info(f"Updated Excel file in Google Drive: {self.google_sheet_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating Google Sheet: {e}")
            return False
    
    def download_excel_from_google_drive(self) -> bool:
        """Download the latest Excel file from Google Drive and overwrite local copy"""
        if not self.drive_service:
            logger.warning("Google Drive service not available")
            return False
        
        try:
            logger.info(f"Downloading Excel file from Google Drive: {self.google_sheet_id}")
            
            # Request the file content (get_media for native files, not export_media)
            request = self.drive_service.files().get_media(
                fileId=self.google_sheet_id
            )
            
            # Download the file content
            excel_content = request.execute()
            
            # Save to local file
            with open(LOCAL_EXCEL_FILE, 'wb') as f:
                f.write(excel_content)
            
            logger.info(f"Successfully downloaded Excel file from Google Drive")
            
            # Reload the local inventory after downloading
            self.load_local_inventory()
            return True
            
        except Exception as e:
            logger.error(f"Error downloading Excel from Google Drive: {e}")
            return False
    
    def update_instrument_amount(self, instrument_name: str, new_amount: str) -> bool:
        """Update the amount of a specific instrument locally and in Google Sheets"""
        try:
            if self.inventory_data is None:
                self.load_local_inventory()
            
            # Find the instrument in local data
            instrument_found = False
            for idx, row in self.inventory_data.iterrows():
                # Check against the 'Наименование' column (column 1)
                current_name = bot.safe_get_text(row, 1) if len(row) > 1 else bot.safe_get_text(row, 0)
                if current_name.lower() == instrument_name.lower():
                    # Update local Excel file - amount is in 'Количество' column (column 5)
                    # Convert to float first to avoid dtype warning
                    self.inventory_data.iloc[idx, 5] = float(new_amount)
                    
                    # Save to local Excel file and update Google Sheet
                    self.save_local_inventory()
                    self.update_google_sheet()
                    
                    instrument_found = True
                    logger.info(f"Updated {instrument_name} amount to {new_amount}")
                    break
            
            if not instrument_found:
                logger.error(f"Instrument '{instrument_name}' not found")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating instrument amount: {e}")
            return False
    
    def save_local_inventory(self):
        """Save current inventory data to local Excel file"""
        try:
            if self.inventory_data is not None:
                # Clean data before saving
                df_to_save = self.inventory_data.copy()
                df_to_save = df_to_save.fillna(0)
                
                # For text columns, replace 0 with empty string
                for col in df_to_save.columns:
                    if df_to_save[col].dtype == 'object':  # Text columns
                        df_to_save[col] = df_to_save[col].replace(0, '')
                
                df_to_save.to_excel(LOCAL_EXCEL_FILE, index=False)
                logger.info("Saved inventory data to local Excel file")
        except Exception as e:
            logger.error(f"Error saving local inventory: {e}")
    
    def get_google_sheet_url(self) -> str:
        """Get the URL of the Google Sheet"""
        if self.google_sheet_id:
            return f"https://docs.google.com/spreadsheets/d/{self.google_sheet_id}"
        return "Google Sheet not created yet"

    def safe_get_text(self, row, col_index: int, default: str = "") -> str:
        """Safely get text value from row, handling NaN values"""
        try:
            if len(row) > col_index:
                value = row.iloc[col_index]
                if pd.isna(value) or value == 0:
                    return default
                return str(value).strip()
            return default
        except:
            return default

# Initialize bot
bot = InventoryBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    keyboard = [
        [InlineKeyboardButton("📦 Просмотр инвентаря", callback_data="view_inventory")],
        [InlineKeyboardButton("🔍 Поиск инструментов", callback_data="search_instruments")],
        [InlineKeyboardButton("🆕 Добавить инструмент", callback_data="add_new_instrument")],
        [InlineKeyboardButton("🔗 Ссылка на таблицу", callback_data="show_sheet_link")],
        [InlineKeyboardButton("🔄 Синхронизация", callback_data="force_sync")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🏢 **Добро пожаловать в Bes Saiman Group!** 🎉\n\n"
        "🔧 **Система управления инвентарем инструментов**\n\n"
        "📋 Здесь вы можете:\n"
        "• 📦 Просматривать весь инвентарь\n"
        "• 🔍 Искать нужные инструменты\n"
        "• 🆕 Добавлять новые инструменты\n"
        "• ✏️ Редактировать количество\n"
        "• 🔄 Синхронизировать с Google Таблицей\n\n"
        "Выберите нужную функцию:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_sheet_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Google Sheet link"""
    query = update.callback_query
    await query.answer()
    
    sheet_url = bot.get_google_sheet_url()
    
    await query.edit_message_text(
        f"🔗 Ссылка на Google Таблицу\n\n"
        f"📊 Таблица: {sheet_url}\n\n"
        f"📄 Файл: {LOCAL_EXCEL_FILE}\n"
        f"📊 Инструментов: {len(bot.inventory_data) if bot.inventory_data is not None else 0}\n\n"
        f"Нажмите на ссылку выше, чтобы открыть таблицу в браузере.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
        ])
    )
    """Show debug information"""
    query = update.callback_query
    await query.answer()
    
    debug_text = f"🔍 **Debug Information**\n\n"
    debug_text += f"📁 **Local Excel File:** {'✅ Found' if os.path.exists(LOCAL_EXCEL_FILE) else '❌ Not found'}\n"
    debug_text += f"📊 **Data Loaded:** {len(bot.inventory_data) if bot.inventory_data is not None else 0} instruments\n"
    debug_text += f"📋 **Service Account:** {'✅ Available' if os.path.exists('service_account.json') else '❌ Not found'}\n"
    debug_text += f"🌐 **Google Sheet:** {'✅ Created' if bot.google_sheet_id else '❌ Not created'}\n"
    
    if bot.google_sheet_id:
        debug_text += f"🔗 **Sheet URL:** {bot.get_google_sheet_url()}\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        debug_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def add_new_instrument(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начать процесс добавления нового инструмента"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    bot.user_states[user_id] = {
        'state': 'adding_instrument',
        'step': 'name',
        'data': {}
    }
    
    await query.edit_message_text(
        "🆕 **Добавление нового инструмента**\n\n"
        "📝 **Шаг 1/6: Название инструмента**\n\n"
        "Введите название нового инструмента:\n\n"
        "💡 **Подсказка:** Используйте кнопки ниже для навигации",
        parse_mode='Markdown'
    )
    
    # Отправить кнопки отдельным сообщением
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "🔧 **Навигация:**",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_instrument_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать введенное название инструмента"""
    user_id = update.effective_user.id
    
    if user_id not in bot.user_states or bot.user_states[user_id]['state'] != 'adding_instrument':
        return
    
    if bot.user_states[user_id]['step'] != 'name':
        return
    
    instrument_name = update.message.text.strip()
    
    if len(instrument_name) < 2:
        await update.message.reply_text(
            "❌ **Ошибка!**\n\n"
            "Название инструмента должно содержать минимум 2 символа.\n"
            "Попробуйте снова:",
            parse_mode='Markdown'
        )
        return
    
    bot.user_states[user_id]['data']['name'] = instrument_name
    bot.user_states[user_id]['step'] = 'model'
    
    keyboard = [
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_model")],
        [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_name")],
        [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **Название сохранено:** `{instrument_name}`\n\n"
        f"📝 **Шаг 2/6: Модель**\n\n"
        f"Введите модель инструмента:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_instrument_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать введенную модель инструмента"""
    user_id = update.effective_user.id
    
    if user_id not in bot.user_states or bot.user_states[user_id]['state'] != 'adding_instrument':
        return
    
    if bot.user_states[user_id]['step'] != 'model':
        return
    
    model = update.message.text.strip()
    
    if model.lower() == '/skip':
        model = ''
    
    bot.user_states[user_id]['data']['model'] = model
    bot.user_states[user_id]['step'] = 'manufacturer'
    
    keyboard = [
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_manufacturer")],
        [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_model")],
        [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **Модель сохранена:** `{model if model else 'Не указана'}`\n\n"
        f"📝 **Шаг 3/6: Производитель**\n\n"
        f"Введите производителя инструмента:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_instrument_manufacturer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать введенного производителя инструмента"""
    user_id = update.effective_user.id
    
    if user_id not in bot.user_states or bot.user_states[user_id]['state'] != 'adding_instrument':
        return
    
    if bot.user_states[user_id]['step'] != 'manufacturer':
        return
    
    manufacturer = update.message.text.strip()
    
    if manufacturer.lower() == '/skip':
        manufacturer = ''
    
    bot.user_states[user_id]['data']['manufacturer'] = manufacturer
    bot.user_states[user_id]['step'] = 'quantity'
    
    keyboard = [
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_quantity")],
        [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_manufacturer")],
        [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **Производитель сохранен:** `{manufacturer if manufacturer else 'Не указан'}`\n\n"
        f"📝 **Шаг 4/6: Количество**\n\n"
        f"Введите количество инструментов:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_instrument_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать введенное количество инструментов"""
    user_id = update.effective_user.id
    
    if user_id not in bot.user_states or bot.user_states[user_id]['state'] != 'adding_instrument':
        return
    
    if bot.user_states[user_id]['step'] != 'quantity':
        return
    
    quantity_text = update.message.text.strip()
    
    if quantity_text.lower() == '/skip':
        quantity = 0
    else:
        try:
            quantity = int(quantity_text)
            if quantity < 0:
                raise ValueError("Количество не может быть отрицательным")
        except ValueError:
            await update.message.reply_text(
                "❌ **Ошибка!**\n\n"
                "Пожалуйста, введите корректное число для количества.\n"
                "Попробуйте снова:",
                parse_mode='Markdown'
            )
            return
    
    bot.user_states[user_id]['data']['quantity'] = quantity
    bot.user_states[user_id]['step'] = 'image_url'
    
    keyboard = [
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_image_url")],
        [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_quantity")],
        [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **Количество сохранено:** `{quantity}` шт.\n\n"
        f"📝 **Шаг 5/6: Ссылка на изображение**\n\n"
        f"Введите публичную ссылку на изображение инструмента:\n\n"
        f"💡 **Подсказка:** Пример: https://example.com/image.jpg",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_instrument_image_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать ссылку на изображение инструмента"""
    user_id = update.effective_user.id
    
    if user_id not in bot.user_states or bot.user_states[user_id]['state'] != 'adding_instrument':
        return
    
    if bot.user_states[user_id]['step'] != 'image_url':
        return
    
    image_url_text = update.message.text.strip()
    
    # Проверяем /skip ПЕРВЫМ!
    if image_url_text.lower() == '/skip':
        image_url = ''
    elif image_url_text.startswith(('http://', 'https://')):
        image_url = image_url_text
    else:
        await update.message.reply_text(
            "❌ **Ошибка!**\n\n"
            "Пожалуйста, введите корректную ссылку на изображение.\n"
            "Ссылка должна начинаться с http:// или https://\n"
            "Попробуйте снова:",
            parse_mode='Markdown'
        )
        return
    
    bot.user_states[user_id]['data']['image_url'] = image_url
    bot.user_states[user_id]['step'] = 'characteristics'
    
    keyboard = [
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_characteristics")],
        [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_image_url")],
        [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **Ссылка на изображение сохранена:** `{image_url if image_url else 'Не указана'}`\n\n"
        f"📝 **Шаг 6/6: Характеристики**\n\n"
        f"Введите дополнительные характеристики инструмента:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_instrument_characteristics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать характеристики инструмента"""
    user_id = update.effective_user.id
    
    print(f"🔍 handle_instrument_characteristics called for user {user_id}")
    print(f"📊 user_states: {bot.user_states.get(user_id, 'NOT_FOUND')}")
    
    if user_id not in bot.user_states or bot.user_states[user_id]['state'] != 'adding_instrument':
        print(f"❌ User {user_id} not in adding_instrument state")
        return
    
    if bot.user_states[user_id]['step'] != 'characteristics':
        print(f"❌ User {user_id} not on characteristics step, step is: {bot.user_states[user_id].get('step', 'UNKNOWN')}")
        return
    
    text = update.message.text.strip() if update.message.text else ''
    print(f"✏️ Processing characteristics for user {user_id}, text: '{text}'")
    
    if text.lower() == '/skip':
        print(f"⏭️ User {user_id} skipped characteristics")
        bot.user_states[user_id]['data']['characteristics'] = ''
    else:
        bot.user_states[user_id]['data']['characteristics'] = text
    
    # Сохранить через save_new_instrument
    print(f"💾 Calling save_new_instrument for user {user_id}")
    await save_new_instrument(update, context)

async def handle_instrument_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать загруженное изображение инструмента"""
    user_id = update.effective_user.id
    
    print(f"DEBUG: handle_instrument_image called for user {user_id}")
    print(f"DEBUG: user_states: {bot.user_states.get(user_id, 'NOT_FOUND')}")
    
    if user_id not in bot.user_states or bot.user_states[user_id]['state'] != 'adding_instrument':
        print(f"DEBUG: User {user_id} not in adding_instrument state")
        return
    
    if bot.user_states[user_id]['step'] != 'image':
        print(f"DEBUG: User {user_id} not in image step, current step: {bot.user_states[user_id]['step']}")
        return
    
    print(f"DEBUG: Processing image for user {user_id}")
    
    if update.message.photo:
        print(f"DEBUG: Photo received, processing...")
        # Получить изображение
        photo = update.message.photo[-1]  # Берем самое большое изображение
        
        # Получить следующий номер изображения (максимальный номер + 1)
        max_number = bot.inventory_data['№'].max() if not bot.inventory_data.empty else 0
        next_image_number = max_number + 1
        image_filename = f"image{next_image_number}.png"
        
        print(f"DEBUG: Saving image as {image_filename}")
        
        # Скачать изображение
        file = await context.bot.get_file(photo.file_id)
        await file.download_to_drive(image_filename)
        
        bot.user_states[user_id]['data']['image'] = image_filename
        
        await update.message.reply_text(
            f"✅ **Изображение сохранено:** `{image_filename}`\n\n"
            f"🔄 **Сохранение инструмента...**",
            parse_mode='Markdown'
        )
        
        # Сохранить инструмент
        await save_new_instrument(update, context)
        
    elif update.message.text and update.message.text.strip().lower() == '/skip':
        print(f"DEBUG: Skip command received")
        # Пользователь пропустил изображение
        await save_new_instrument(update, context)
        
    else:
        print(f"DEBUG: Invalid input received")
        await update.message.reply_text(
            "❌ **Ошибка!**\n\n"
            "Пожалуйста, отправьте изображение или нажмите /skip для пропуска.",
            parse_mode='Markdown'
        )

async def save_new_instrument(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сохранить новый инструмент в Excel и обновить данные"""
    user_id = update.effective_user.id
    
    print(f"💾 save_new_instrument called for user {user_id}")
    
    if user_id not in bot.user_states or bot.user_states[user_id]['state'] != 'adding_instrument':
        print(f"❌ save_new_instrument: User {user_id} not in adding_instrument state")
        return
    
    data = bot.user_states[user_id]['data'].copy()  # КОПИРОВАТЬ данные!
    print(f"📋 Data copied: {data}")
    
    try:
        # Получить следующий номер инструмента (максимальный номер + 1)
        max_number = bot.inventory_data['№'].max() if not bot.inventory_data.empty else 0
        next_number = max_number + 1
        
        # Создать новую строку для Excel
        new_row = {
            '№': next_number,  # Номер инструмента
            'Наименование': data['name'],  # Название
            'Модель': data['model'],  # Модель
            'Компания производителя': data['manufacturer'],  # Производитель
            'Характеристика ': data.get('characteristics', ''),  # Характеристика
            'Количество': data['quantity'],  # Количество
            'ImageURL': data.get('image_url', '')  # Ссылка на изображение
        }
        
        # Добавить строку в DataFrame
        new_df = pd.DataFrame([new_row])
        bot.inventory_data = pd.concat([bot.inventory_data, new_df], ignore_index=True)
        
        # Сохранить в Excel
        bot.save_local_inventory()
        
        # Обновить Google Sheet
        bot.update_google_sheet()
        
        # Очистить состояние пользователя ПОСЛЕ сохранения данных
        del bot.user_states[user_id]
        
        # Отправить подтверждение - используем query для callback
        if update.callback_query:
            await update.callback_query.answer("✅ Инструмент успешно добавлен!")
            await update.callback_query.message.reply_text(
                f"🎉 **Инструмент успешно добавлен!**\n\n"
                f"📋 **Детали:**\n"
                f"• **Название:** `{data['name']}`\n"
                f"• **Модель:** `{data['model'] if data['model'] else 'Не указана'}`\n"
                f"• **Производитель:** `{data['manufacturer'] if data['manufacturer'] else 'Не указан'}`\n"
                f"• **Количество:** `{data['quantity']}`\n"
                f"• **Характеристики:** `{data.get('characteristics', 'Не указаны')}`\n"
                f"• **Изображение:** `{data.get('image_url', 'Не указано')}`\n\n"
                f"✅ Инструмент добавлен в систему и синхронизирован с Google Sheets!\n"
                f"🌐 **Веб-сайт обновится автоматически при следующем обновлении страницы.**",
                parse_mode='Markdown'
            )
        elif update.message:
            await update.message.reply_text(
                f"🎉 **Инструмент успешно добавлен!**\n\n"
                f"📋 **Детали:**\n"
                f"• **Название:** `{data['name']}`\n"
                f"• **Модель:** `{data['model'] if data['model'] else 'Не указана'}`\n"
                f"• **Производитель:** `{data['manufacturer'] if data['manufacturer'] else 'Не указан'}`\n"
                f"• **Количество:** `{data['quantity']}`\n"
                f"• **Характеристики:** `{data.get('characteristics', 'Не указаны')}`\n"
                f"• **Изображение:** `{data.get('image_url', 'Не указано')}`\n\n"
                f"✅ Инструмент добавлен в систему и синхронизирован с Google Sheets!\n"
                f"🌐 **Веб-сайт обновится автоматически при следующем обновлении страницы.**",
                parse_mode='Markdown'
            )
        
        logger.info(f"Added new instrument: {data['name']}")
        
    except Exception as e:
        logger.error(f"Error saving new instrument: {e}")
        if update.callback_query:
            await update.callback_query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
        elif update.message:
            await update.message.reply_text(
                f"❌ **Ошибка при сохранении!**\n\n"
                f"Произошла ошибка: `{str(e)}`\n\n"
                f"Попробуйте снова или обратитесь к администратору.",
                parse_mode='Markdown'
            )
        
        # Очистить состояние пользователя при ошибке
        if user_id in bot.user_states:
            del bot.user_states[user_id]

async def cancel_adding_instrument(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменить добавление инструмента"""
    user_id = update.effective_user.id
    
    if user_id in bot.user_states:
        del bot.user_states[user_id]
    
    # Проверяем, вызывается ли из callback query или из текстового сообщения
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ **Добавление инструмента отменено**\n\n"
            "Вы можете начать заново, нажав кнопку 'Добавить инструмент' в главном меню.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Если вызывается из текстового сообщения
        await update.message.reply_text(
            "❌ **Добавление инструмента отменено**\n\n"
            "Вы можете начать заново, нажав кнопку 'Добавить инструмент' в главном меню.",
            parse_mode='Markdown'
        )

async def search_instruments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search instruments by name"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔍 **Поиск инструментов**\n\n"
        "Введите название инструмента для поиска.\n"
        "Поиск работает по частичному совпадению.\n\n"
        "Пример: 'термо' или 'контроллер'",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # Store search state
    context.user_data['searching'] = True

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle search query with pagination"""
    if not context.user_data.get('searching', False):
        return
    
    search_term = update.message.text.strip().lower()
    inventory_data = bot.inventory_data
    
    if inventory_data is None or inventory_data.empty:
        await update.message.reply_text("❌ Данные инвентаря не найдены.")
        return
    
    # Search in instrument names (column 2)
    matches = []
    for idx, row in inventory_data.iterrows():
        instrument_name = bot.safe_get_text(row, 1).lower()
        if search_term in instrument_name and instrument_name:
            matches.append((idx, row))
    
    if not matches:
        await update.message.reply_text(
            f"🔍 **Результаты поиска**\n\n"
            f"По запросу '{search_term}' ничего не найдено.\n\n"
            "Попробуйте другой поисковый запрос."
        )
        context.user_data['searching'] = False
        return
    
    # Store search results in context for pagination
    context.user_data['search_results'] = matches
    context.user_data['search_term'] = search_term
    context.user_data['search_page'] = 0
    
    # Show first page of results
    await show_search_results(update, context, 0)
    
    # Clear search state
    context.user_data['searching'] = False

async def show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """Show paginated search results"""
    matches = context.user_data.get('search_results', [])
    search_term = context.user_data.get('search_term', '')
    
    if not matches:
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text("❌ Результаты поиска не найдены.")
        else:
            await update.callback_query.edit_message_text("❌ Результаты поиска не найдены.")
        return
    
    # Pagination settings
    items_per_page = 5
    total_pages = (len(matches) + items_per_page - 1) // items_per_page
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(matches))
    
    # Format results for current page
    result_text = f"🔍 **Результаты поиска**\n\n"
    result_text += f"Поиск: '{search_term}'\n"
    result_text += f"Найдено: **{len(matches)}** инструментов\n"
    result_text += f"Страница {page + 1} из {total_pages}\n\n"
    
    keyboard = []
    for i, (idx, row) in enumerate(matches[start_idx:end_idx], start_idx + 1):
        name = bot.safe_get_text(row, 1, "Неизвестно")
        amount = bot.safe_get_text(row, 5, "0")
        
        result_text += f"**{i}.** {name}\n"
        result_text += f"   Количество: {amount}\n\n"
        
        keyboard.append([InlineKeyboardButton(
            f"🔧 {name[:35]}...", 
            callback_data=f"instrument_{idx}"
        )])
    
    # Add pagination buttons
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"search_page_{page - 1}"))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"search_page_{page + 1}"))
    if pagination_buttons:
        keyboard.append(pagination_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Handle both message and callback query
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(
            result_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.callback_query.edit_message_text(
            result_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show statistics and charts"""
    query = update.callback_query
    await query.answer()
    
    inventory_data = bot.inventory_data
    if inventory_data is None or inventory_data.empty:
        await query.edit_message_text("❌ Данные инвентаря не найдены.")
        return
    
    # Calculate statistics
    total_instruments = len(inventory_data)
    
    # Count by manufacturer (column 4)
    manufacturers = {}
    total_amount = 0
    low_stock = 0
    
    for idx, row in inventory_data.iterrows():
        if len(row) > 4:
            manufacturer = str(row.iloc[4]).strip()
            if manufacturer and manufacturer != 'nan':
                manufacturers[manufacturer] = manufacturers.get(manufacturer, 0) + 1
        
        if len(row) > 6:
            try:
                amount = float(bot.safe_get_text(row, 6, "0"))
                total_amount += amount
                if amount < 5:  # Low stock threshold
                    low_stock += 1
            except:
                pass
    
    # Top manufacturers
    top_manufacturers = sorted(manufacturers.items(), key=lambda x: x[1], reverse=True)[:5]
    
    stats_text = f"📊 **Статистика инвентаря**\n\n"
    stats_text += f"📦 **Общая информация:**\n"
    stats_text += f"• Всего инструментов: {total_instruments}\n"
    stats_text += f"• Общее количество: {total_amount:.0f}\n"
    stats_text += f"• Низкий запас (<5): {low_stock}\n\n"
    
    stats_text += f"🏭 **Топ производители:**\n"
    for i, (manufacturer, count) in enumerate(top_manufacturers, 1):
        stats_text += f"{i}. {manufacturer}: {count} шт.\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        stats_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def chart_manufacturers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show manufacturers chart"""
    query = update.callback_query
    await query.answer()
    
    inventory_data = bot.inventory_data
    if inventory_data is None or inventory_data.empty:
        await query.edit_message_text("❌ Данные инвентаря не найдены.")
        return
    
    # Count by manufacturer (column 4)
    manufacturers = {}
    for idx, row in inventory_data.iterrows():
        if len(row) > 4:
            manufacturer = str(row.iloc[4]).strip()
            if manufacturer and manufacturer != 'nan':
                manufacturers[manufacturer] = manufacturers.get(manufacturer, 0) + 1
    
    # Top manufacturers
    top_manufacturers = sorted(manufacturers.items(), key=lambda x: x[1], reverse=True)[:10]
    
    chart_text = f"📈 **График по производителям**\n\n"
    chart_text += f"Топ-10 производителей:\n\n"
    
    for i, (manufacturer, count) in enumerate(top_manufacturers, 1):
        # Create simple bar chart with emojis
        bar_length = min(count, 20)  # Limit bar length
        bar = "█" * bar_length
        chart_text += f"{i:2}. {manufacturer[:20]:<20} {count:3} {bar}\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к статистике", callback_data="statistics")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        chart_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def chart_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show stock levels chart"""
    query = update.callback_query
    await query.answer()
    
    inventory_data = bot.inventory_data
    if inventory_data is None or inventory_data.empty:
        await query.edit_message_text("❌ Данные инвентаря не найдены.")
        return
    
    # Analyze stock levels
    stock_levels = {"Низкий (<5)": 0, "Средний (5-20)": 0, "Высокий (>20)": 0}
    total_amount = 0
    
    for idx, row in inventory_data.iterrows():
        if len(row) > 6:
            try:
                amount = float(bot.safe_get_text(row, 6, "0"))
                total_amount += amount
                if amount < 5:
                    stock_levels["Низкий (<5)"] += 1
                elif amount <= 20:
                    stock_levels["Средний (5-20)"] += 1
                else:
                    stock_levels["Высокий (>20)"] += 1
            except:
                pass
    
    chart_text = f"📉 **График уровней запасов**\n\n"
    chart_text += f"Общее количество: {total_amount:.0f}\n\n"
    
    for level, count in stock_levels.items():
        percentage = (count / len(inventory_data)) * 100 if len(inventory_data) > 0 else 0
        bar_length = int(percentage / 2)  # Scale for display
        bar = "█" * bar_length
        chart_text += f"{level:<15} {count:3} ({percentage:4.1f}%) {bar}\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к статистике", callback_data="statistics")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        chart_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def view_table(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show inventory table"""
    query = update.callback_query
    await query.answer()
    
    inventory_data = bot.inventory_data
    if inventory_data is None or inventory_data.empty:
        await query.edit_message_text("❌ Данные инвентаря не найдены.")
        return
    
    # Get current page from callback data or set to 0
    current_page = 0
    if query.data.startswith("table_page_"):
        try:
            current_page = int(query.data.split('_')[2])  # table_page_0 -> 0
        except (ValueError, IndexError):
            current_page = 0
    items_per_page = 10
    
    start_idx = current_page * items_per_page
    end_idx = start_idx + items_per_page
    
    total_items = len(inventory_data)
    total_pages = (total_items + items_per_page - 1) // items_per_page
    
    # Create table header
    table_text = f"📋 **Таблица инвентаря**\n\n"
    table_text += f"Страница {current_page + 1} из {total_pages}\n"
    table_text += f"Показано {start_idx + 1}-{min(end_idx, total_items)} из {total_items}\n\n"
    
    # Add table header
    table_text += "```\n"
    table_text += f"{'№':<3} {'Название':<25} {'Количество':<10} {'Производитель':<15}\n"
    table_text += "-" * 65 + "\n"
    
    # Add table rows
    for i, idx in enumerate(range(start_idx, min(end_idx, total_items)), start_idx + 1):
        row = inventory_data.iloc[idx]
        name = bot.safe_get_text(row, 1, "0")[:22]
        amount = bot.safe_get_text(row, 5, "0")[:8]
        manufacturer = bot.safe_get_text(row, 3, "0")[:12]
        
        table_text += f"{i:<3} {name:<25} {amount:<10} {manufacturer:<15}\n"
    
    table_text += "```\n"
    
    # Create pagination buttons
    keyboard = []
    pagination_buttons = []
    if current_page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"table_page_{current_page - 1}"))
    if current_page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"table_page_{current_page + 1}"))
    if pagination_buttons:
        keyboard.append(pagination_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        table_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings menu"""
    query = update.callback_query
    await query.answer()
    
    settings_text = f"⚙️ **Настройки системы**\n\n"
    settings_text += f"📊 **Загружено данных:** {len(bot.inventory_data) if bot.inventory_data is not None else 0} инструментов\n"
    settings_text += f"📋 **Сервисный аккаунт:** {'✅ Доступен' if os.path.exists('service_account.json') else '❌ Не найден'}\n"
    settings_text += f"🌐 **Google Таблица:** {'✅ Подключена' if bot.google_sheet_id else '❌ Не подключена'}\n\n"
    
    settings_text += f"🔗 **Ссылка на Google Таблицу:**\n"
    settings_text += f"{bot.get_google_sheet_url()}\n\n"
    
    settings_text += f"📄 **Файл Excel:** {LOCAL_EXCEL_FILE}\n"
    settings_text += f"🔄 **Автосинхронизация:** ✅ Включена\n\n"
    settings_text += f"Все изменения автоматически сохраняются в Google Таблице!"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Принудительная синхронизация", callback_data="force_sync")],
        [InlineKeyboardButton("📸 Все изображения", callback_data="send_all_images")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        settings_text,
        reply_markup=reply_markup
    )

async def force_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force sync with Google Drive"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Reload local data
        bot.load_local_inventory()
        
        # Upload to Google Sheet
        success = bot.update_google_sheet()
        
        if success:
            await query.edit_message_text(
                "🎉 **Синхронизация завершена успешно!**\n\n"
                f"📊 **Загружено:** {len(bot.inventory_data)} инструментов\n"
                f"🔗 **Google Таблица:** {bot.get_google_sheet_url()}\n\n"
                "✨ Все данные обновлены в Google Sheets!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
                ])
            )
        else:
            await query.edit_message_text(
                "⚠️ **Ошибка синхронизации**\n\n"
                "Не удалось обновить Google Таблицу.\n"
                "Проверьте подключение к Google API.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
                ])
            )
    except Exception as e:
        await query.edit_message_text(
            f"💥 **Ошибка синхронизации:**\n\n"
            f"`{str(e)}`\n\n"
            "Проверьте подключение к Google API.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
            ])
        )

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to main menu"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📦 Просмотр инвентаря", callback_data="view_inventory")],
        [InlineKeyboardButton("🔍 Поиск инструментов", callback_data="search_instruments")],
        [InlineKeyboardButton("🆕 Добавить инструмент", callback_data="add_new_instrument")],
        [InlineKeyboardButton("🔗 Ссылка на таблицу", callback_data="show_sheet_link")],
        [InlineKeyboardButton("🔄 Синхронизация", callback_data="force_sync")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🏢 **Добро пожаловать в Bes Saiman Group!** 🎉\n\n"
        "🔧 **Система управления инвентарем инструментов**\n\n"
        "📋 Здесь вы можете:\n"
        "• 📦 Просматривать весь инвентарь\n"
        "• 🔍 Искать нужные инструменты\n"
        "• 🆕 Добавлять новые инструменты\n"
        "• ✏️ Редактировать количество\n"
        "• 🔄 Синхронизировать с Google Таблицей\n\n"
        "Выберите нужную функцию:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def view_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show inventory menu with instrument buttons (paginated)"""
    query = update.callback_query
    await query.answer()
    
    # Get page number from callback data or default to 0
    page = 0
    if query.data.startswith("page_"):
        page = int(query.data.split("_")[1])
    
    # Use local inventory data
    inventory_data = bot.inventory_data
    
    if inventory_data is None or inventory_data.empty:
        await query.edit_message_text("❌ Данные инвентаря не найдены. Проверьте локальный Excel файл.")
        return
    
    # Filter valid instruments
    valid_instruments = []
    for idx, row in inventory_data.iterrows():
        instrument_name = bot.safe_get_text(row, 1) if len(row) > 1 else bot.safe_get_text(row, 0)
        if instrument_name and instrument_name != 'nan' and instrument_name != 'None':
            valid_instruments.append((idx, instrument_name))
    
    # Calculate pagination
    instruments_per_page = 5
    total_pages = (len(valid_instruments) + instruments_per_page - 1) // instruments_per_page
    start_idx = page * instruments_per_page
    end_idx = min(start_idx + instruments_per_page, len(valid_instruments))
    
    # Create buttons for current page
    keyboard = []
    for i in range(start_idx, end_idx):
        idx, instrument_name = valid_instruments[i]
        keyboard.append([InlineKeyboardButton(
            f"🔧 {instrument_name}", 
            callback_data=f"instrument_{idx}"
        )])
    
    # Add pagination buttons
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"page_{page+1}"))
    
    if pagination_buttons:
        keyboard.append(pagination_buttons)
    
    # Add back button
    keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    page_info = f" (Страница {page + 1} из {total_pages})" if total_pages > 1 else ""
    await query.edit_message_text(
        f"📦 **Управление инвентарем**{page_info}\n\n"
        f"Показано инструментов {start_idx + 1}-{end_idx} из {len(valid_instruments)}\n\n"
        "Выберите инструмент для просмотра деталей:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_instrument_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed information about a specific instrument"""
    query = update.callback_query
    await query.answer()
    
    instrument_idx = int(query.data.split('_')[1])
    inventory_data = bot.inventory_data
    
    if inventory_data is None or inventory_data.empty:
        await query.edit_message_text("❌ Данные инвентаря недоступны.")
        return
    
    row = inventory_data.iloc[instrument_idx]
    instrument_name = bot.safe_get_text(row, 1) if len(row) > 1 else bot.safe_get_text(row, 0)  # Наименование column
    amount = bot.safe_get_text(row, 5, "0")  # Количество column
    
    # Build info message
    info_text = f"🔧 **{instrument_name}**\n\n"
    info_text += f"📊 **Количество в наличии:** {amount} шт.\n\n"
    
    # Add only specific columns (exclude empty columns A-J)
    important_columns = ['Наименование', 'Модель', 'Компания производителя', 'Характеристика ', 'Количество']
    for col in important_columns:
        if col in inventory_data.columns:
            col_idx = inventory_data.columns.get_loc(col)
            if col_idx < len(row):
                value = str(row.iloc[col_idx]).strip()
                if value and value != 'nan' and value != '0':
                    info_text += f"📝 **{col}:** {value}\n"
    
    # Try to find and send image
    image_sent = False
    try:
        # First check for ImageURL column
        if 'ImageURL' in inventory_data.columns:
            image_url_idx = inventory_data.columns.get_loc('ImageURL')
            if image_url_idx < len(row):
                image_url = str(row.iloc[image_url_idx]).strip()
                if image_url and image_url != 'nan' and image_url != '':
                    logger.info(f"Found image URL: {image_url}")
                    try:
                        await query.message.reply_photo(
                            photo=image_url,
                            caption=info_text,
                            parse_mode='Markdown'
                        )
                        image_sent = True
                        logger.info(f"Successfully sent image from URL: {image_url}")
                    except Exception as e:
                        logger.error(f"Failed to send image from URL {image_url}: {e}")
                        info_text += f"🖼️ **Изображение:** [Ссылка]({image_url})\n"
        
        # If no ImageURL or failed, try local files
        if not image_sent:
            # Use the instrument number from the "№" column to match image names
            instrument_number = str(int(row.iloc[0])) if len(row) > 0 and pd.notna(row.iloc[0]) else str(instrument_idx + 1)
            
            # Try local file first (since we have images locally)
            if instrument_number:
                # Try different image formats
                image_paths = [
                    f"image{instrument_number}.png",
                    f"image{instrument_number}.jpg", 
                    f"image{instrument_number}.jpeg",
                    f"image{instrument_number}.avif"
                ]
                
                for image_path in image_paths:
                    if os.path.exists(image_path):
                        logger.info(f"Found local image: {image_path}")
                        try:
                            # Send image first
                            with open(image_path, 'rb') as photo:
                                await query.message.reply_photo(photo=photo, caption=info_text, parse_mode='Markdown')
                            image_sent = True
                            logger.info(f"Successfully sent image: {image_path}")
                            break
                        except Exception as img_error:
                            logger.error(f"Failed to send image {image_path}: {img_error}")
                            # If it's an AVIF file that failed, try to convert it
                            if image_path.endswith('.avif'):
                                try:
                                    # Try to convert AVIF to PNG using a simple approach
                                    import subprocess
                                    png_path = image_path.replace('.avif', '_converted.png')
                                    # Use sips (macOS built-in) to convert
                                    result = subprocess.run(['sips', '-s', 'format', 'png', image_path, '--out', png_path], 
                                                          capture_output=True, text=True)
                                    if result.returncode == 0 and os.path.exists(png_path):
                                        logger.info(f"Converted AVIF to PNG: {png_path}")
                                        with open(png_path, 'rb') as photo:
                                            await query.message.reply_photo(photo=photo, caption=info_text, parse_mode='Markdown')
                                        image_sent = True
                                        logger.info(f"Successfully sent converted image: {png_path}")
                                        # Clean up converted file
                                        os.remove(png_path)
                                        break
                                except Exception as convert_error:
                                    logger.error(f"Failed to convert AVIF: {convert_error}")
                            continue
    except Exception as e:
        logger.error(f"Error processing image: {e}")
    
    # If no image was sent, send text only
    if not image_sent:
        # Add a note about missing image
        info_text += f"\n🖼️ **Изображение:** Недоступно"
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить количество", callback_data=f"edit_{instrument_idx}")],
            [InlineKeyboardButton("🗑️ Удалить инструмент", callback_data=f"delete_{instrument_idx}")],
            [InlineKeyboardButton("🔙 Назад к инвентарю", callback_data="view_inventory")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            info_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Image was sent successfully, just add the keyboard buttons
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить количество", callback_data=f"edit_{instrument_idx}")],
            [InlineKeyboardButton("🗑️ Удалить инструмент", callback_data=f"delete_{instrument_idx}")],
            [InlineKeyboardButton("🔙 Назад к инвентарю", callback_data="view_inventory")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send the keyboard as a separate message
        await query.message.reply_text(
            "Выберите действие:",
            reply_markup=reply_markup
        )

async def start_edit_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start edit mode for an instrument"""
    query = update.callback_query
    await query.answer()
    
    instrument_idx = int(query.data.split('_')[1])
    inventory_data = bot.inventory_data
    
    if inventory_data is None or inventory_data.empty:
        await query.edit_message_text("❌ Данные инвентаря недоступны.")
        return
    
    instrument_name = str(inventory_data.iloc[instrument_idx].iloc[1]).strip() if len(inventory_data.iloc[instrument_idx]) > 1 else str(inventory_data.iloc[instrument_idx].iloc[0]).strip()
    current_amount = str(inventory_data.iloc[instrument_idx].iloc[5]).strip() if len(inventory_data.iloc[instrument_idx]) > 5 else "0"
    
    # Store the instrument index in context for the next message
    context.user_data['editing_instrument'] = instrument_idx
    
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data=f"instrument_{instrument_idx}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✏️ **Режим редактирования**\n\n"
        f"🔧 **Инструмент:** {instrument_name}\n"
        f"📊 **Текущее количество:** {current_amount} шт.\n\n"
        f"💬 **Введите новое количество:**",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_amount_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle amount update from user message"""
    if 'editing_instrument' not in context.user_data:
        await update.message.reply_text("⚠️ Инструмент не выбран для редактирования.")
        return
    
    new_amount = update.message.text.strip()
    instrument_idx = context.user_data['editing_instrument']
    
    # Validate the amount (basic validation)
    try:
        float(new_amount)  # Check if it's a valid number
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число для количества.")
        return
    
    inventory_data = bot.inventory_data
    if inventory_data is None or inventory_data.empty:
        await update.message.reply_text("⚠️ Данные инвентаря недоступны.")
        return
    
    instrument_name = str(inventory_data.iloc[instrument_idx].iloc[1]).strip() if len(inventory_data.iloc[instrument_idx]) > 1 else str(inventory_data.iloc[instrument_idx].iloc[0]).strip()
    
    # Update the amount in Google Sheets
    success = bot.update_instrument_amount(instrument_name, new_amount)
    
    if success:
        # Reload data to get fresh information
        bot.load_local_inventory()
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к инвентарю", callback_data="view_inventory")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎉 **Количество успешно обновлено!**\n\n"
            f"🔧 **Инструмент:** {instrument_name}\n"
            f"📊 **Новое количество:** {new_amount} шт.\n\n"
            f"✨ Данные сохранены локально и синхронизированы с Google Таблицей!\n"
            f"🌐 **Веб-сайт обновится автоматически при следующем обновлении страницы.**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("⚠️ Не удалось обновить количество. Попробуйте снова.")
    
    # Clear the editing state
    del context.user_data['editing_instrument']


async def delete_instrument(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete an instrument from inventory"""
    query = update.callback_query
    await query.answer()
    
    instrument_idx = int(query.data.split('_')[1])
    inventory_data = bot.inventory_data
    
    if inventory_data is None or inventory_data.empty:
        await query.edit_message_text("❌ Данные инвентаря недоступны.")
        return
    
    if instrument_idx >= len(inventory_data):
        await query.edit_message_text("❌ Инструмент не найден.")
        return
    
    # Get instrument name for confirmation
    instrument_name = str(inventory_data.iloc[instrument_idx].iloc[1]).strip() if len(inventory_data.iloc[instrument_idx]) > 1 else str(inventory_data.iloc[instrument_idx].iloc[0]).strip()
    
    # Store the instrument index for confirmation
    context.user_data['deleting_instrument'] = instrument_idx
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{instrument_idx}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"instrument_{instrument_idx}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🗑️ **Подтверждение удаления**\n\n"
        f"🔧 **Инструмент:** {instrument_name}\n\n"
        f"⚠️ **Внимание!** Это действие нельзя отменить.\n"
        f"Инструмент будет удален из локального файла и Google Drive.\n\n"
        f"Вы уверены, что хотите удалить этот инструмент?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def confirm_delete_instrument(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirm and execute instrument deletion"""
    query = update.callback_query
    await query.answer()
    
    instrument_idx = int(query.data.split('_')[2])
    inventory_data = bot.inventory_data
    
    if inventory_data is None or inventory_data.empty:
        await query.edit_message_text("❌ Данные инвентаря недоступны.")
        return
    
    if instrument_idx >= len(inventory_data):
        await query.edit_message_text("❌ Инструмент не найден.")
        return
    
    # Get instrument name before deletion
    instrument_name = str(inventory_data.iloc[instrument_idx].iloc[1]).strip() if len(inventory_data.iloc[instrument_idx]) > 1 else str(inventory_data.iloc[instrument_idx].iloc[0]).strip()
    
    try:
        # Delete the row from DataFrame
        bot.inventory_data = inventory_data.drop(inventory_data.index[instrument_idx]).reset_index(drop=True)
        
        # Save to local Excel file
        bot.save_local_inventory()
        
        # Update Google Sheet
        bot.update_google_sheet()
        
        # Clear user data
        if 'deleting_instrument' in context.user_data:
            del context.user_data['deleting_instrument']
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к инвентарю", callback_data="view_inventory")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Инструмент успешно удален!**\n\n"
            f"🔧 **Удаленный инструмент:** {instrument_name}\n\n"
            f"📊 Данные обновлены локально и синхронизированы с Google Drive!\n"
            f"🌐 **Веб-сайт обновится автоматически при следующем обновлении страницы.**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error deleting instrument: {e}")
        await query.edit_message_text(
            f"❌ **Ошибка при удалении инструмента**\n\n"
            f"Произошла ошибка: {str(e)}\n\n"
            f"Попробуйте снова или обратитесь к администратору.",
            parse_mode='Markdown'
        )

async def add_back_to_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вернуться к шагу ввода названия"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id in bot.user_states and bot.user_states[user_id]['state'] == 'adding_instrument':
        bot.user_states[user_id]['step'] = 'name'
        
        keyboard = [
            [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🆕 **Добавление нового инструмента**\n\n"
            "📝 **Шаг 1/6: Название инструмента**\n\n"
            "Введите название нового инструмента:\n\n"
            "💡 **Подсказка:** Используйте кнопки ниже для навигации",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def add_back_to_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вернуться к шагу ввода модели"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id in bot.user_states and bot.user_states[user_id]['state'] == 'adding_instrument':
        bot.user_states[user_id]['step'] = 'model'
        data = bot.user_states[user_id]['data']
        
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_model")],
            [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_name")],
            [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Название:** `{data['name']}`\n\n"
            f"📝 **Шаг 2/6: Модель**\n\n"
            f"Введите модель инструмента:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def add_back_to_manufacturer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вернуться к шагу ввода производителя"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id in bot.user_states and bot.user_states[user_id]['state'] == 'adding_instrument':
        bot.user_states[user_id]['step'] = 'manufacturer'
        data = bot.user_states[user_id]['data']
        
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_manufacturer")],
            [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_model")],
            [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Название:** `{data['name']}`\n"
            f"✅ **Модель:** `{data['model'] if data['model'] else 'Не указана'}`\n\n"
            f"📝 **Шаг 3/6: Производитель**\n\n"
            f"Введите производителя инструмента:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def add_back_to_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вернуться к шагу ввода количества"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id in bot.user_states and bot.user_states[user_id]['state'] == 'adding_instrument':
        bot.user_states[user_id]['step'] = 'quantity'
        data = bot.user_states[user_id]['data']
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_manufacturer")],
            [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Название:** `{data['name']}`\n"
            f"✅ **Модель:** `{data['model'] if data['model'] else 'Не указана'}`\n"
            f"✅ **Производитель:** `{data['manufacturer'] if data['manufacturer'] else 'Не указан'}`\n\n"
            f"📝 **Шаг 4/6: Количество**\n\n"
            f"Введите количество инструментов:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def add_back_to_image_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вернуться к шагу ввода ссылки на изображение"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id in bot.user_states and bot.user_states[user_id]['state'] == 'adding_instrument':
        bot.user_states[user_id]['step'] = 'image_url'
        data = bot.user_states[user_id]['data']
        
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_image_url")],
            [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_quantity")],
            [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Название:** `{data['name']}`\n"
            f"✅ **Модель:** `{data['model'] if data['model'] else 'Не указана'}`\n"
            f"✅ **Производитель:** `{data['manufacturer'] if data['manufacturer'] else 'Не указан'}`\n"
            f"✅ **Количество:** `{data['quantity']}` шт.\n\n"
            f"📝 **Шаг 5/6: Ссылка на изображение**\n\n"
            f"Введите публичную ссылку на изображение инструмента:\n\n"
            f"💡 **Подсказка:** Пример: https://example.com/image.jpg",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def add_back_to_characteristics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вернуться к шагу ввода характеристик"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id in bot.user_states and bot.user_states[user_id]['state'] == 'adding_instrument':
        bot.user_states[user_id]['step'] = 'characteristics'
        data = bot.user_states[user_id]['data']
        
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_characteristics")],
            [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_image_url")],
            [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Название:** `{data['name']}`\n"
            f"✅ **Модель:** `{data['model'] if data['model'] else 'Не указана'}`\n"
            f"✅ **Производитель:** `{data['manufacturer'] if data['manufacturer'] else 'Не указан'}`\n"
            f"✅ **Количество:** `{data['quantity']}` шт.\n"
            f"✅ **Изображение:** `{data.get('image_url', 'Не указано')}`\n\n"
            f"📝 **Шаг 6/6: Характеристики**\n\n"
            f"Введите дополнительные характеристики инструмента:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all callback queries"""
    query = update.callback_query
    
    if query.data == "view_inventory":
        await view_inventory(update, context)
    elif query.data.startswith("page_"):
        await view_inventory(update, context)
    elif query.data == "search_instruments":
        await search_instruments(update, context)
    elif query.data.startswith("search_page_"):
        page = int(query.data.split("_")[2])
        await show_search_results(update, context, page)
    elif query.data == "show_sheet_link":
        await show_sheet_link(update, context)
    elif query.data == "force_sync":
        await force_sync(update, context)
    elif query.data == "add_new_instrument":
        await add_new_instrument(update, context)
    elif query.data == "back_to_menu":
        await back_to_menu(update, context)
    elif query.data.startswith("instrument_"):
        await show_instrument_info(update, context)
    elif query.data.startswith("edit_"):
        await start_edit_mode(update, context)
    elif query.data.startswith("delete_"):
        await delete_instrument(update, context)
    elif query.data.startswith("confirm_delete_"):
        await confirm_delete_instrument(update, context)
    elif query.data == "save_instrument":
        await save_new_instrument(update, context)
    elif query.data == "add_cancel":
        await cancel_adding_instrument(update, context)
    elif query.data == "add_back_to_name":
        await add_back_to_name(update, context)
    elif query.data == "add_back_to_model":
        await add_back_to_model(update, context)
    elif query.data == "add_back_to_manufacturer":
        await add_back_to_manufacturer(update, context)
    elif query.data == "add_back_to_quantity":
        await add_back_to_quantity(update, context)
    elif query.data == "add_back_to_image_url":
        await add_back_to_image_url(update, context)
    elif query.data == "add_back_to_characteristics":
        await add_back_to_characteristics(update, context)
    elif query.data == "add_skip_model":
        # Пропустить модель
        user_id = update.effective_user.id
        if user_id in bot.user_states:
            bot.user_states[user_id]['data']['model'] = ''
            bot.user_states[user_id]['step'] = 'manufacturer'
            # Перейти к следующему шагу
            await query.answer()
            keyboard = [
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_manufacturer")],
                [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_model")],
                [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            data = bot.user_states[user_id]['data']
            await query.message.reply_text(
                f"✅ **Модель пропущена**\n\n"
                f"📝 **Шаг 3/6: Производитель**\n\n"
                f"Введите производителя инструмента:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    elif query.data == "add_skip_manufacturer":
        # Пропустить производителя
        user_id = update.effective_user.id
        if user_id in bot.user_states:
            bot.user_states[user_id]['data']['manufacturer'] = ''
            bot.user_states[user_id]['step'] = 'quantity'
            await query.answer()
            keyboard = [
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_quantity")],
                [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_manufacturer")],
                [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            data = bot.user_states[user_id]['data']
            await query.message.reply_text(
                f"✅ **Производитель пропущен**\n\n"
                f"📝 **Шаг 4/6: Количество**\n\n"
                f"Введите количество инструментов:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    elif query.data == "add_skip_quantity":
        # Пропустить количество - НЕЛЬЗЯ! Количество обязательно
        await query.answer("❌ Количество не может быть пропущено! Пожалуйста, введите количество.", show_alert=True)
    elif query.data == "add_skip_image_url":
        # Пропустить ссылку на изображение
        user_id = update.effective_user.id
        if user_id in bot.user_states:
            bot.user_states[user_id]['data']['image_url'] = ''
            bot.user_states[user_id]['step'] = 'characteristics'
            await query.answer()
            keyboard = [
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="add_skip_characteristics")],
                [InlineKeyboardButton("🔙 Назад", callback_data="add_back_to_image_url")],
                [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(
                f"✅ **Ссылка на изображение пропущена**\n\n"
                f"📝 **Шаг 6/6: Характеристики**\n\n"
                f"Введите дополнительные характеристики инструмента:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    elif query.data == "add_skip_characteristics":
        # Пропустить характеристики и сохранить
        user_id = update.effective_user.id
        if user_id in bot.user_states:
            bot.user_states[user_id]['data']['characteristics'] = ''
            # Сохранить инструмент
            await save_new_instrument(update, context)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages - either search, amount update, or adding instrument"""
    user_id = update.effective_user.id
    
    # Обработка изображений для добавления инструмента (ПЕРВЫМ ДЕЛОМ!)
    if user_id in bot.user_states and bot.user_states[user_id]['state'] == 'adding_instrument':
        if bot.user_states[user_id]['step'] == 'image':
            if update.message.photo:
                await handle_instrument_image(update, context)
                return
            elif update.message.text and update.message.text.strip().lower() == '/skip':
                await handle_instrument_image(update, context)
                return
            else:
                # Если пользователь отправил что-то другое вместо изображения
                await update.message.reply_text(
                    "❌ **Ошибка!**\n\n"
                    "Пожалуйста, отправьте изображение или нажмите /skip для пропуска.",
                    parse_mode='Markdown'
                )
                return
    
    # Проверяем, находится ли пользователь в процессе добавления инструмента
    if user_id in bot.user_states and bot.user_states[user_id]['state'] == 'adding_instrument':
        step = bot.user_states[user_id]['step']
        
        if step == 'name':
            await handle_instrument_name(update, context)
        elif step == 'model':
            await handle_instrument_model(update, context)
        elif step == 'manufacturer':
            await handle_instrument_manufacturer(update, context)
        elif step == 'quantity':
            await handle_instrument_quantity(update, context)
        elif step == 'image_url':
            await handle_instrument_image_url(update, context)
        elif step == 'characteristics':
            await handle_instrument_characteristics(update, context)
        elif step == 'image':
            # Если пользователь отправил /skip для изображения
            if update.message.text and update.message.text.strip().lower() == '/skip':
                await save_new_instrument(update, context)
            else:
                await update.message.reply_text(
                    "❌ **Ошибка!**\n\n"
                    "Пожалуйста, отправьте изображение или нажмите /skip для пропуска.",
                    parse_mode='Markdown'
                )
        return
    
    # Проверяем, находится ли пользователь в процессе добавления инструмента и отправил /skip
    if update.message.text and update.message.text.strip().lower() == '/skip':
        if user_id in bot.user_states and bot.user_states[user_id]['state'] == 'adding_instrument':
            step = bot.user_states[user_id]['step']
            if step == 'model':
                await handle_instrument_model(update, context)
            elif step == 'manufacturer':
                await handle_instrument_manufacturer(update, context)
            elif step == 'quantity':
                await handle_instrument_quantity(update, context)
            elif step == 'characteristics':
                await handle_instrument_characteristics(update, context)
            # Для изображения обработка уже есть выше
        return
    
    # Проверяем, находится ли пользователь в процессе добавления инструмента и отправил /cancel
    if update.message.text and update.message.text.strip().lower() == '/cancel':
        await cancel_adding_instrument(update, context)
        return
    
    # Старая логика для поиска и редактирования
    if context.user_data.get('searching', False):
        await handle_search(update, context)
    elif 'editing_instrument' in context.user_data:
        await handle_amount_update(update, context)
    else:
        await update.message.reply_text(
            "Используйте /start для доступа к меню бота."
        )

def main():
    """Main function to run the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_text_message))  # Обработка изображений
    
    # Bot is already initialized with local data and Google Sheet
    
    # Start the bot
    logger.info("Starting Telegram bot...")
    application.run_polling()

if __name__ == '__main__':
    main()
