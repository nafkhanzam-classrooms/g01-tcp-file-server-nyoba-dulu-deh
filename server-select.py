import socket
import select
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


def broadcast(message, sender_sock, client_map):
    for fd, info in client_map.items():
        if info['sock'] is not sender_sock:
            try:
                send_text(info['sock'], f'[broadcast] {message}')
            except Exception:
                pass

def handle_command(cmd, sock, addr, client_map):
    parts = cmd.split()
    verb = parts[0] if parts else ''

    if verb == '/list':
        logging.info(f'{addr} → /list')
        files = os.listdir(STORAGE)
        send_text(sock, '\n'.join(files) if files else '(no files)')

    elif verb == '/upload' and len(parts) > 1:
        name = sanitize(parts[1], sock, addr)
        if not name:
            return
        dest = os.path.join(STORAGE, name)
        logging.info(f'{addr} → /upload {name}')
        receive_file(sock, dest)
        send_text(sock, f'Upload complete: {name}')
        broadcast(f'{addr} uploaded {name}', sock, client_map)
        logging.info(f'Saved {name} from {addr}')

    elif verb == '/download' and len(parts) > 1:
        name = sanitize(parts[1], sock, addr)
        if not name:
            return
        path = os.path.join(STORAGE, name)
        logging.info(f'{addr} → /download {name}')
        if not os.path.isfile(path):
            send_text(sock, f'ERROR: {name} not found')
            return
        send_text(sock, 'OK')
        send_file(sock, path)
        logging.info(f'Sent {name} to {addr}')

    else:
        send_text(sock, f'ERROR: unknown command "{cmd}"')

def main():
    os.makedirs(STORAGE, exist_ok=True)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(10)
    logging.info(f'[SELECT] Listening on {HOST}:{PORT}')

    watch = [server_sock]
    client_map = {}

    try:
        while True:
            readable, _, exceptional = select.select(watch, [], watch, 1.0)

            for sock in readable:
                if sock is server_sock:
                    conn, addr = server_sock.accept()
                    conn.setblocking(True)
                    watch.append(conn)
                    client_map[conn.fileno()] = {'sock': conn, 'addr': addr}
                    send_text(conn, 'Welcome! Connected to select-based server.')
                    broadcast(f'New client joined: {addr}', conn, client_map)
                    logging.info(f'New client: {addr}')

                else:
                    addr = client_map.get(sock.fileno(), {}).get('addr', '?')
                    try:
                        cmd = recv_text(sock)
                        if cmd is None:
                            raise ConnectionResetError
                        handle_command(cmd, sock, addr, client_map)
                    except (ConnectionResetError, BrokenPipeError, OSError):
                        logging.info(f'Client disconnected: {addr}')
                        broadcast(f'Client left: {addr}', sock, client_map)
                        watch.remove(sock)
                        client_map.pop(sock.fileno(), None)
                        sock.close()

            for sock in exceptional:
                addr = client_map.get(sock.fileno(), {}).get('addr', '?')
                logging.warning(f'Socket error for {addr}')
                watch.remove(sock)
                client_map.pop(sock.fileno(), None)
                sock.close()

    except KeyboardInterrupt:
        logging.info('Shutting down.')
    finally:
        for info in client_map.values():
            info['sock'].close()
        server_sock.close()


if __name__ == '__main__':
    main()