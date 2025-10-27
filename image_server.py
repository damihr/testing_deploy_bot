#!/usr/bin/env python3
"""
Public Image Server for Bes Saiman Inventory Bot
Сервер для публичного доступа к изображениям инструментов
"""

import os
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import threading
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageHandler(SimpleHTTPRequestHandler):
    """Обработчик запросов для изображений"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.getcwd(), **kwargs)
    
    def do_GET(self):
        """Обработка GET запросов"""
        try:
            # Парсим URL
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            
            # Если запрашивается изображение
            if path.startswith('/image') and (path.endswith('.png') or path.endswith('.jpg') or path.endswith('.jpeg')):
                # Убираем ведущий слеш
                image_path = path[1:]
                
                if os.path.exists(image_path):
                    # Отправляем изображение
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'public, max-age=3600')
                    self.end_headers()
                    
                    with open(image_path, 'rb') as f:
                        self.wfile.write(f.read())
                    
                    logger.info(f"✅ Served image: {image_path}")
                else:
                    # Изображение не найдено
                    self.send_response(404)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'Image not found')
                    logger.warning(f"❌ Image not found: {image_path}")
            else:
                # Обычная обработка файлов
                super().do_GET()
                
        except Exception as e:
            logger.error(f"❌ Error serving request: {e}")
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Internal server error')
    
    def log_message(self, format, *args):
        """Переопределяем логирование"""
        logger.info(f"{self.address_string()} - {format % args}")

class ImageServer:
    """Класс для управления сервером изображений"""
    
    def __init__(self, port=8080):
        self.port = port
        self.server = None
        self.server_thread = None
        self.running = False
    
    def start(self):
        """Запуск сервера"""
        try:
            self.server = HTTPServer(('0.0.0.0', self.port), ImageHandler)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            self.running = True
            
            logger.info(f"🚀 Image server started on port {self.port}")
            logger.info(f"📸 Images available at: http://localhost:{self.port}/image[N].png")
            logger.info(f"🌐 Public access: http://[YOUR_IP]:{self.port}/image[N].png")
            
        except Exception as e:
            logger.error(f"❌ Error starting image server: {e}")
            raise
    
    def stop(self):
        """Остановка сервера"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.running = False
            logger.info("🛑 Image server stopped")
    
    def get_image_url(self, image_filename):
        """Получить URL изображения"""
        # Для локального тестирования
        local_url = f"http://localhost:{self.port}/{image_filename}"
        
        # Для публичного доступа (замените YOUR_IP на ваш IP)
        # public_url = f"http://YOUR_IP:{self.port}/{image_filename}"
        
        return local_url

def get_public_ip():
    """Получить публичный IP адрес"""
    try:
        import requests
        response = requests.get('https://api.ipify.org', timeout=5)
        return response.text.strip()
    except:
        return "YOUR_IP"

def main():
    """Основная функция"""
    print("🖼️  Bes Saiman Image Server")
    print("=" * 40)
    
    # Получаем публичный IP
    public_ip = get_public_ip()
    print(f"🌐 Your public IP: {public_ip}")
    
    # Создаем и запускаем сервер
    server = ImageServer(port=8080)
    
    try:
        server.start()
        
        print(f"\n✅ Server is running!")
        print(f"📱 Local access: http://localhost:8080/image[N].png")
        print(f"🌍 Public access: http://{public_ip}:8080/image[N].png")
        print(f"\n📸 Available images:")
        
        # Показываем доступные изображения
        image_files = [f for f in os.listdir('.') if f.startswith('image') and f.endswith(('.png', '.jpg', '.jpeg'))]
        image_files.sort(key=lambda x: int(''.join(filter(str.isdigit, x))))
        
        for img in image_files[:10]:  # Показываем первые 10
            print(f"   • http://{public_ip}:8080/{img}")
        
        if len(image_files) > 10:
            print(f"   ... and {len(image_files) - 10} more images")
        
        print(f"\n🔄 Server is running. Press Ctrl+C to stop.")
        
        # Держим сервер запущенным
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Stopping server...")
        server.stop()
        print("✅ Server stopped")

if __name__ == "__main__":
    main()
