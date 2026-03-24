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

# poll event flags
POLL_IN  = select.POLLIN  | select.POLLPRI
POLL_ERR = select.POLLERR | select.POLLHUP | select.POLLNVAL

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
        send_text(sock, 'ERROR: invalid filename')
        return None
    return name


def broadcast(message, sender_fd, fd_map):
    for fd, info in fd_map.items():
        if fd != sender_fd:
            try:
                send_text(info['sock'], f'[broadcast] {message}')
            except Exception:
                pass

def handle_command(cmd, sock, addr, fd, fd_map):
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
        broadcast(f'{addr} uploaded {name}', fd, fd_map)

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

    else:
        send_text(sock, f'ERROR: unknown command "{cmd}"')

def remove_client(fd, poller, fd_map):
    info = fd_map.pop(fd, None)
    poller.unregister(fd)
    if info:
        addr = info['addr']
        info['sock'].close()
        logging.info(f'Disconnected: {addr}')
        return addr
    return fd

def main():
    os.makedirs(STORAGE, exist_ok=True)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(10)
    server_fd = server_sock.fileno()
    logging.info(f'[POLL] Listening on {HOST}:{PORT}')

    poller = select.poll()
    poller.register(server_fd, POLL_IN)

    fd_map = {}

    try:
        while True:
            events = poller.poll(1000)   # 1 s timeout

            for fd, event in events:
                if event & POLL_ERR:
                    if fd == server_fd:
                        raise RuntimeError('Error on server socket')
                    addr = remove_client(fd, poller, fd_map)
                    broadcast(f'Client {addr} dropped (error)', fd, fd_map)
                    continue

                if fd == server_fd:
                    conn, addr = server_sock.accept()
                    conn.setblocking(True)
                    cfd = conn.fileno()
                    fd_map[cfd] = {'sock': conn, 'addr': addr}
                    poller.register(cfd, POLL_IN)
                    send_text(conn, 'Welcome! Connected to poll-based server.')
                    broadcast(f'New client: {addr}', cfd, fd_map)
                    logging.info(f'New client: {addr}')

                else:
                    info = fd_map.get(fd)
                    if not info:
                        continue
                    sock, addr = info['sock'], info['addr']
                    try:
                        cmd = recv_text(sock)
                        if cmd is None:
                            raise ConnectionResetError
                        handle_command(cmd, sock, addr, fd, fd_map)
                    except (ConnectionResetError, BrokenPipeError, OSError):
                        remove_client(fd, poller, fd_map)
                        broadcast(f'Client {addr} left', fd, fd_map)

    except KeyboardInterrupt:
        logging.info('Shutting down.')
    finally:
        for info in fd_map.values():
            info['sock'].close()
        server_sock.close()


if __name__ == '__main__':
    main()