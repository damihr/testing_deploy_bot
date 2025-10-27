#!/usr/bin/env python3
"""
Auto-start Image Server
Автоматически запускает сервер изображений при старте бота
"""

import subprocess
import time
import os
import logging
from image_server import ImageServer

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def start_image_server():
    """Запуск сервера изображений"""
    try:
        server = ImageServer(port=8080)
        server.start()
        
        # Получаем публичный IP
        try:
            import requests
            public_ip = requests.get('https://api.ipify.org', timeout=5).text.strip()
        except:
            public_ip = "YOUR_IP"
        
        logger.info(f"🚀 Image server started successfully!")
        logger.info(f"🌐 Public access: http://{public_ip}:8080/image[N].png")
        
        return server
        
    except Exception as e:
        logger.error(f"❌ Error starting image server: {e}")
        return None

def main():
    """Основная функция"""
    print("🖼️  Starting Bes Saiman Image Server...")
    
    server = start_image_server()
    
    if server:
        print("✅ Image server is running!")
        print("📱 You can now start the Telegram bot")
        print("🔄 Press Ctrl+C to stop the server")
        
        try:
            # Держим сервер запущенным
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping image server...")
            server.stop()
            print("✅ Image server stopped")
    else:
        print("❌ Failed to start image server")

if __name__ == "__main__":
    main()
