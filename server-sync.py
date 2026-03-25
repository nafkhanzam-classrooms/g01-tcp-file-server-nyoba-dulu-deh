import socket
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

def sanitize(raw_name, sock, addr):
    name = os.path.basename(raw_name)
    if name in ('', '.', '..'):
        logging.warning(f'{addr} sent invalid filename: {raw_name!r}')
        send_text(sock, 'ERROR: invalid filename')
        return None
    return name

def handle_command(cmd, sock, addr):
    parts = cmd.split()
    verb = parts[0] if parts else ''

    if verb == '/list':
        logging.info(f'{addr} → /list')
        files = os.listdir(STORAGE)
        payload = '\n'.join(files) if files else '(no files on server)'
        send_text(sock, payload)

    elif verb == '/upload' and len(parts) > 1:
        name = sanitize(parts[1], sock, addr)
        if not name:
            return
        dest = os.path.join(STORAGE, name)
        logging.info(f'{addr} → /upload {name}')
        receive_file(sock, dest)
        send_text(sock, f'Upload complete: {name}')
        logging.info(f'Saved {name} from {addr}')

    elif verb == '/download' and len(parts) > 1:
        name = sanitize(parts[1], sock, addr)
        if not name:
            return
        path = os.path.join(STORAGE, name)
        logging.info(f'{addr} → /download {name}')
        if not os.path.isfile(path):
            send_text(sock, f'ERROR: {name} not found on server')
            logging.warning(f'{addr} requested missing file: {name}')
            return
        send_text(sock, 'OK')
        send_file(sock, path)
        logging.info(f'Sent {name} to {addr}')

    else:
        send_text(sock, f'ERROR: unknown command "{cmd}"')
        logging.warning(f'{addr} sent unknown command: {cmd!r}')

def main():
    os.makedirs(STORAGE, exist_ok=True)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)
    logging.info(f'[SYNC] Listening on {HOST}:{PORT}')

    try:
        while True:
            logging.info('Waiting for next client…')
            conn, addr = srv.accept()
            logging.info(f'Connected: {addr}')
            send_text(conn, 'Welcome! Connected to sync server.')

            try:
                while True:
                    cmd = recv_text(conn)
                    if cmd is None:
                        break
                    handle_command(cmd, conn, addr)
            except Exception as ex:
                logging.error(f'Error with {addr}: {ex}')
            finally:
                conn.close()
                logging.info(f'Disconnected: {addr}')

    except KeyboardInterrupt:
        logging.info('Shutting down.')
    finally:
        srv.close()


if __name__ == '__main__':
    main()