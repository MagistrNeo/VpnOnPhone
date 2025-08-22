import asyncio
import threading
import random
from typing import List, Optional

class ProxyServer:
    def __init__(self):
        self.port = 8881
        self.is_running = False
        self.server = None
        self.blocked_sites: Optional[List[bytes]] = None
        self.tasks: List[asyncio.Task] = []
        self._android_initialized = False
        self._android_classes = {}

    def set_blocked_sites(self, sites: List[str]):
        """Установка заблокированных сайтов"""
        self.blocked_sites = [site.encode() for site in sites]

    async def fragment_data(self, local_reader, remote_writer):
        """Фрагментация данных для обхода блокировок"""
        head = await local_reader.read(5)
        data = await local_reader.read(1500)
        parts = []

        if self.blocked_sites and all(data.find(site) == -1 for site in self.blocked_sites):
            remote_writer.write(head + data)
            await remote_writer.drain()
            return

        while data:
            part_len = random.randint(1, len(data))
            parts.append(
                bytes.fromhex("1603") +
                bytes([random.randint(0, 255)]) +
                int(part_len).to_bytes(2, byteorder='big') +
                data[0:part_len]
            )
            data = data[part_len:]

        remote_writer.write(b''.join(parts))
        await remote_writer.drain()

    async def pipe(self, reader, writer):
        """Передача данных между сокетами"""
        while not reader.at_eof() and not writer.is_closing():
            try:
                writer.write(await reader.read(1500))
                await writer.drain()
            except:
                break
        writer.close()

    async def handle_connection(self, local_reader, local_writer):
        """Обработка нового подключения"""
        http_data = await local_reader.read(1500)

        try:
            method, target = http_data.split(b"\r\n")[0].split(b" ")[0:2]
            host, port = target.split(b":")
        except:
            local_writer.close()
            return

        if method != b"CONNECT":
            local_writer.close()
            return

        local_writer.write(b'HTTP/1.1 200 OK\n\n')
        await local_writer.drain()

        try:
            remote_reader, remote_writer = await asyncio.open_connection(host.decode(), int(port))
        except:
            local_writer.close()
            return

        if port == b'443':
            await self.fragment_data(local_reader, remote_writer)

        self.tasks.append(asyncio.create_task(self.pipe(local_reader, remote_writer)))
        self.tasks.append(asyncio.create_task(self.pipe(remote_reader, local_writer)))

    async def start_async(self):
        """Асинхронный запуск сервера"""
        self.server = await asyncio.start_server(
            self.handle_connection,
            '0.0.0.0',
            self.port
        )
        self.is_running = True
        async with self.server:
            await self.server.serve_forever()

    def start(self):
        """Запуск сервера в отдельном потоке"""
        if not self.is_running:
            threading.Thread(
                target=self._run_server,
                daemon=True
            ).start()
            return f"Прокси запущен на порту {self.port}"
        return "Прокси уже запущен"

    def _run_server(self):
        """Запуск asyncio в отдельном потоке"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start_async())

    def stop(self):
        """Остановка сервера"""
        if self.is_running and self.server:
            for task in self.tasks:
                task.cancel()
            self.server.close()
            self.is_running = False
            return "Прокси остановлен"
        return "Прокси не был запущен"

# Экземпляр для использования из Kotlin
proxy_instance = ProxyServer()