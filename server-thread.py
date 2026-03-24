import socket
import threading
import struct
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

HOST = '127.0.0.1'
PORT = 9090
STORAGE = 'server_storage'
CHUNK = 4096

registry_lock = threading.Lock()
connected_clients: list = []

def _recv_exact(sock, n):
    buf = b''
    while len(buf) < n:
        piece = sock.recv(n - len(buf))
        if not piece:
            return None
        buf += piece
    return buf


def send_text(sock, text):
    data = text.encode('utf-8')
    sock.sendall(struct.pack('>I', len(data)) + data)


def recv_text(sock):
    hdr = _recv_exact(sock, 4)
    if not hdr:
        return None
    length = struct.unpack('>I', hdr)[0]
    body = _recv_exact(sock, length)
    return body.decode('utf-8') if body else None


def receive_file(sock, dest_path):
    with open(dest_path, 'wb') as fh:
        while True:
            hdr = _recv_exact(sock, 4)
            if not hdr:
                break
            length = struct.unpack('>I', hdr)[0]
            if length == 0:
                break
            chunk = _recv_exact(sock, length)
            if not chunk:
                break
            fh.write(chunk)


def send_file(sock, src_path):
    with open(src_path, 'rb') as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            sock.sendall(struct.pack('>I', len(chunk)) + chunk)
    sock.sendall(struct.pack('>I', 0))

def broadcast(message, exclude=None):
    with registry_lock:
        targets = [c for c in connected_clients if c is not exclude]
    for client in targets:
        try:
            client.write(f'[broadcast] {message}')
        except Exception:
            pass

class ClientHandler(threading.Thread):
    def __init__(self, sock, addr):
        super().__init__(daemon=True)
        self.sock = sock
        self.addr = addr

    def write(self, text):
        send_text(self.sock, text)

    def _sanitize(self, raw_name):
        name = os.path.basename(raw_name)
        if name in ('', '.', '..'):
            logging.warning(f'{self.addr} invalid filename: {raw_name!r}')
            self.write('ERROR: invalid filename')
            return None
        return name

    def _handle(self, cmd):
        parts = cmd.split()
        verb = parts[0] if parts else ''

        if verb == '/list':
            logging.info(f'{self.addr} → /list')
            files = os.listdir(STORAGE)
            self.write('\n'.join(files) if files else '(no files)')

        elif verb == '/upload' and len(parts) > 1:
            name = self._sanitize(parts[1])
            if not name:
                return
            dest = os.path.join(STORAGE, name)
            logging.info(f'{self.addr} → /upload {name}')
            receive_file(self.sock, dest)
            self.write(f'Upload complete: {name}')
            broadcast(f'{self.addr} uploaded {name}', exclude=self)
            logging.info(f'Saved {name} from {self.addr}')

        elif verb == '/download' and len(parts) > 1:
            name = self._sanitize(parts[1])
            if not name:
                return
            path = os.path.join(STORAGE, name)
            logging.info(f'{self.addr} → /download {name}')
            if not os.path.isfile(path):
                self.write(f'ERROR: {name} not found')
                logging.warning(f'Missing file requested: {name} by {self.addr}')
                return
            self.write('OK')
            send_file(self.sock, path)
            logging.info(f'Sent {name} to {self.addr}')

        else:
            self.write(f'ERROR: unknown command "{cmd}"')

    def run(self):
        try:
            while True:
                cmd = recv_text(self.sock)
                if cmd is None:
                    break
                self._handle(cmd)
        except (ConnectionResetError, BrokenPipeError, OSError) as ex:
            logging.warning(f'{self.addr} connection lost: {ex}')
        except Exception as ex:
            logging.error(f'Unexpected error from {self.addr}: {ex}')
        finally:
            self._cleanup()

    def _cleanup(self):
        logging.info(f'Disconnected: {self.addr}')
        with registry_lock:
            if self in connected_clients:
                connected_clients.remove(self)
        try:
            self.sock.close()
        except Exception:
            pass
        broadcast(f'Client {self.addr} has left.', exclude=self)

def main():
    os.makedirs(STORAGE, exist_ok=True)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(10)
    logging.info(f'[THREAD] Listening on {HOST}:{PORT}')

    try:
        while True:
            conn, addr = server_sock.accept()
            handler = ClientHandler(conn, addr)
            with registry_lock:
                connected_clients.append(handler)
            handler.start()
            logging.info(f'New client: {addr}  (active threads: {threading.active_count()})')
            send_text(conn, 'Welcome! Connected to threaded server.')
            broadcast(f'New client joined: {addr}', exclude=handler)

    except KeyboardInterrupt:
        logging.info('Shutting down — closing all clients.')
        with registry_lock:
            for c in connected_clients:
                try:
                    c.sock.shutdown(socket.SHUT_RDWR)
                    c.sock.close()
                except Exception:
                    pass
    finally:
        server_sock.close()
        logging.info('Server closed.')


if __name__ == '__main__':
    main()