#!/usr/bin/env python3
"""
Google Drive Image Uploader
Функции для загрузки изображений в Google Drive и получения публичных URL
"""

import os
import logging
from googleapiclient.http import MediaFileUpload
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DriveUploader:
    def __init__(self, credentials_file='service_account.json'):
        """Инициализация загрузчика Google Drive"""
        self.credentials_file = credentials_file
        self.drive_service = None
        self.folder_id = None  # ID папки для хранения изображений
        self.setup_drive_service()
        self.create_images_folder()
    
    def setup_drive_service(self):
        """Настройка сервиса Google Drive"""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            self.drive_service = build('drive', 'v3', credentials=credentials)
            logger.info("✅ Google Drive service initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error initializing Google Drive service: {e}")
            raise
    
    def create_images_folder(self):
        """Создание папки для изображений инструментов"""
        try:
            # Проверяем, существует ли уже папка
            query = "name='BesSaiman_Images' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            
            if files:
                self.folder_id = files[0]['id']
                logger.info(f"✅ Found existing folder: {self.folder_id}")
            else:
                # Создаем новую папку
                folder_metadata = {
                    'name': 'BesSaiman_Images',
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = self.drive_service.files().create(body=folder_metadata, fields='id').execute()
                self.folder_id = folder.get('id')
                logger.info(f"✅ Created new folder: {self.folder_id}")
                
                # Делаем папку публично доступной
                self.drive_service.permissions().create(
                    fileId=self.folder_id,
                    body={'role': 'reader', 'type': 'anyone'}
                ).execute()
                logger.info("✅ Made folder publicly accessible")
                
        except Exception as e:
            logger.error(f"❌ Error creating/finding images folder: {e}")
            raise
    
    def upload_image(self, local_path, instrument_number=None):
        """
        Загрузка изображения в Google Drive
        
        Args:
            local_path (str): Путь к локальному файлу
            instrument_number (int): Номер инструмента для имени файла
            
        Returns:
            str: Публичный URL изображения
        """
        try:
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"File not found: {local_path}")
            
            # Определяем имя файла
            if instrument_number:
                filename = f"image_{instrument_number}.png"
            else:
                filename = os.path.basename(local_path)
            
            # Метаданные файла
            file_metadata = {
                'name': filename,
                'parents': [self.folder_id]
            }
            
            # Определяем MIME тип
            mime_type = 'image/png'
            if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
                mime_type = 'image/jpeg'
            elif filename.lower().endswith('.gif'):
                mime_type = 'image/gif'
            
            # Загружаем файл
            media = MediaFileUpload(local_path, mimetype=mime_type)
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            logger.info(f"✅ Uploaded {filename} with ID: {file_id}")
            
            # Делаем файл публично доступным
            self.drive_service.permissions().create(
                fileId=file_id,
                body={'role': 'reader', 'type': 'anyone'}
            ).execute()
            
            # Возвращаем публичный URL
            public_url = f"https://drive.google.com/uc?id={file_id}"
            logger.info(f"✅ Created public URL: {public_url}")
            
            return public_url
            
        except Exception as e:
            logger.error(f"❌ Error uploading image {local_path}: {e}")
            raise
    
    def delete_image(self, file_id):
        """
        Удаление изображения из Google Drive
        
        Args:
            file_id (str): ID файла в Google Drive
        """
        try:
            self.drive_service.files().delete(fileId=file_id).execute()
            logger.info(f"✅ Deleted file with ID: {file_id}")
        except Exception as e:
            logger.error(f"❌ Error deleting file {file_id}: {e}")
            raise
    
    def list_images(self):
        """Получение списка всех изображений в папке"""
        try:
            query = f"'{self.folder_id}' in parents and trashed=false"
            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name, createdTime)"
            ).execute()
            return results.get('files', [])
        except Exception as e:
            logger.error(f"❌ Error listing images: {e}")
            raise

def upload_image_to_drive(local_path, instrument_number=None):
    """
    Простая функция для загрузки одного изображения
    
    Args:
        local_path (str): Путь к локальному файлу
        instrument_number (int): Номер инструмента
        
    Returns:
        str: Публичный URL изображения
    """
    uploader = DriveUploader()
    return uploader.upload_image(local_path, instrument_number)

if __name__ == "__main__":
    # Тестирование
    uploader = DriveUploader()
    
    # Показываем информацию о папке
    print(f"📁 Images folder ID: {uploader.folder_id}")
    
    # Список существующих изображений
    images = uploader.list_images()
    print(f"📸 Found {len(images)} existing images:")
    for img in images[:5]:  # Показываем первые 5
        print(f"  - {img['name']} (ID: {img['id']})")
    
    if len(images) > 5:
        print(f"  ... and {len(images) - 5} more")
