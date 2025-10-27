#!/usr/bin/env python3
"""
Update Image URLs in Excel
Обновляет URL изображений в Excel файле для публичного доступа
"""

import pandas as pd
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_public_ip():
    """Получить публичный IP адрес"""
    try:
        import requests
        response = requests.get('https://api.ipify.org', timeout=5)
        return response.text.strip()
    except:
        return "YOUR_IP"

def update_image_urls(excel_file='Расходники 9 октября.xlsx', server_port=8080):
    """Обновить URL изображений в Excel файле"""
    try:
        # Получаем публичный IP
        public_ip = get_public_ip()
        base_url = f"http://{public_ip}:{server_port}"
        
        logger.info(f"🌐 Using base URL: {base_url}")
        
        # Загружаем Excel файл
        df = pd.read_excel(excel_file)
        logger.info(f"📊 Loaded Excel file with {len(df)} rows")
        
        # Проверяем наличие колонки ImageURL
        if 'ImageURL' not in df.columns:
            logger.error("❌ ImageURL column not found in Excel file")
            return False
        
        updated_count = 0
        
        # Обновляем URL для каждого инструмента
        for index, row in df.iterrows():
            if pd.notna(row['№']) and pd.notna(row['Наименование']):
                instrument_number = int(row['№'])
                image_filename = f"image{instrument_number}.png"
                
                # Проверяем, существует ли изображение
                if os.path.exists(image_filename):
                    image_url = f"{base_url}/{image_filename}"
                    df.at[index, 'ImageURL'] = image_url
                    updated_count += 1
                    logger.info(f"✅ Updated URL for instrument #{instrument_number}: {image_url}")
                else:
                    logger.warning(f"⚠️ Image not found: {image_filename}")
        
        # Сохраняем обновленный файл
        df.to_excel(excel_file, index=False)
        logger.info(f"💾 Saved updated Excel file")
        logger.info(f"📸 Updated {updated_count} image URLs")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error updating image URLs: {e}")
        return False

def main():
    """Основная функция"""
    print("🖼️  Image URL Updater for Bes Saiman Inventory")
    print("=" * 50)
    
    # Получаем публичный IP
    public_ip = get_public_ip()
    print(f"🌐 Your public IP: {public_ip}")
    print(f"📸 Image server should be running on: http://{public_ip}:8080")
    
    # Проверяем наличие изображений
    image_files = [f for f in os.listdir('.') if f.startswith('image') and f.endswith(('.png', '.jpg', '.jpeg'))]
    print(f"📁 Found {len(image_files)} image files")
    
    if len(image_files) == 0:
        print("❌ No image files found!")
        return
    
    # Обновляем URL
    print(f"\n🔄 Updating image URLs in Excel...")
    success = update_image_urls()
    
    if success:
        print(f"\n✅ Image URLs updated successfully!")
        print(f"🌐 Images are now accessible at: http://{public_ip}:8080/image[N].png")
        print(f"📱 Telegram bot will now send images via URLs instead of local files")
    else:
        print(f"\n❌ Failed to update image URLs")

if __name__ == "__main__":
    main()
