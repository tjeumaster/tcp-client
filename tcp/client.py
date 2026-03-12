import asyncio
from loguru import logger 

class AsyncTCPClient:
    def __init__(self, host, port, read_timeout=None):
        self.host = host
        self.port = port
        self.read_timeout = read_timeout  # Default is None (Infinite wait)
        
        self.reader = None
        self.writer = None
        
        self.send_queue = asyncio.Queue()
        self.receive_queue = asyncio.Queue()
        self.running = False
        
        self.can_send_next = asyncio.Event()
        self.can_send_next.set()
        
        self.connected_event = asyncio.Event()

    async def start(self):
        self.running = True
        asyncio.create_task(self._keep_alive_loop())
        asyncio.create_task(self._write_loop())
        asyncio.create_task(self._read_loop())
        
        logger.info("Client started. Waiting for connection...")
        await self.connected_event.wait()

    async def _keep_alive_loop(self):
        while self.running:
            if not self.connected_event.is_set():
                try:
                    logger.info(f"Connecting to {self.host}:{self.port}...")
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_connection(self.host, self.port), 
                        timeout=5
                    )
                    logger.info(f"Connected to {self.host}:{self.port}.")
                    self.connected_event.set()
                except (OSError, asyncio.TimeoutError) as e:
                    logger.error(f"Connection failed: {e}. Retrying in 3s...")
                    await asyncio.sleep(3)
            else:
                await asyncio.sleep(1)

    async def _write_loop(self):
        while self.running:
            try:
                await self.connected_event.wait()
                await self.can_send_next.wait()

                message = await self.send_queue.get()
                if message is None: break

                logger.info(f"Sending: {message} to {self.host}:{self.port}")
                self.writer.write(message.encode('utf-8'))
                await self.writer.drain()
                
                self.can_send_next.clear()
                self.send_queue.task_done()

            except (ConnectionResetError, BrokenPipeError, OSError):
                logger.error("Write error. Reconnecting...")
                self._trigger_reconnect()

    async def _read_loop(self):
        while self.running:
            try:
                await self.connected_event.wait()
                
                try:
                    # If self.read_timeout is None, this waits indefinitely (standard behavior)
                    # If it is a number, it waits that many seconds before raising TimeoutError
                    data = await asyncio.wait_for(
                        self.reader.read(4096), 
                        timeout=self.read_timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Read timed out (> {self.read_timeout}s). Reconnecting...")
                    self._trigger_reconnect()
                    continue
                
                if not data:
                    logger.warning("Server closed connection (EOF).")
                    self._trigger_reconnect()
                    continue

                message = data.decode('utf-8')
                logger.info(f"Received: {message} from {self.host}:{self.port}")
                await self.receive_queue.put(message)

            except (ConnectionResetError, BrokenPipeError, OSError):
                logger.error("Read connection lost.")
                self._trigger_reconnect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in read loop: {e}")

    def _trigger_reconnect(self):
        if self.connected_event.is_set():
            self.connected_event.clear()
            if self.writer:
                try:
                    self.writer.close()
                except Exception:
                    pass

    async def send(self, message):
        await self.send_queue.put(message)

    async def receive(self):
        return await self.receive_queue.get()

    def acknowledge(self):
        logger.info("Processing done. Unlocking next send.")
        self.can_send_next.set()

    async def stop(self):
        self.running = False
        self._trigger_reconnect()
        await self.send_queue.put(None)

