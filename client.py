import socket
import struct
import os
import select
import sys

SERVER_HOST = 'localhost'
SERVER_PORT = 9090
STORAGE_DIR = 'client_files'
CHUNK_SIZE = 4096


def pack_message(text):
    encoded = text.encode('utf-8')
    return struct.pack('>I', len(encoded)) + encoded


def unpack_message(sock):
    raw_len = _recv_exact(sock, 4)
    if not raw_len:
        return None
    msg_len = struct.unpack('>I', raw_len)[0]
    data = _recv_exact(sock, msg_len)
    return data.decode('utf-8') if data else None


def _recv_exact(sock, n):
    buffer = b''
    while len(buffer) < n:
        piece = sock.recv(n - len(buffer))
        if not piece:
            return None
        buffer += piece
    return buffer


def upload_file(sock, local_path):
    with open(local_path, 'rb') as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            sock.sendall(struct.pack('>I', len(chunk)) + chunk)
    sock.sendall(struct.pack('>I', 0))


def download_file(sock, save_path):
    os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)
    with open(save_path, 'wb') as fh:
        while True:
            header = _recv_exact(sock, 4)
            if not header:
                break
            length = struct.unpack('>I', header)[0]
            if length == 0:
                break
            chunk = _recv_exact(sock, length)
            if not chunk:
                break
            fh.write(chunk)


def run_client():
    os.makedirs(STORAGE_DIR, exist_ok=True)

    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        conn.connect((SERVER_HOST, SERVER_PORT))
    except ConnectionRefusedError:
        print(f"[!] Cannot reach server at {SERVER_HOST}:{SERVER_PORT}. Is it running?")
        return

    welcome = unpack_message(conn)
    if welcome:
        print(f"[Server] {welcome}")

    print("\nAvailable commands:")
    print("  /list                — list files on server")
    print("  /upload <filepath>   — send a local file to server")
    print("  /download <filename> — fetch a file from server")
    print("  /exit                — disconnect\n")

    try:
        while True:
            sys.stdout.write('you> ')
            sys.stdout.flush()

            readable, _, _ = select.select([conn, sys.stdin], [], [])

            for src in readable:
                if src is conn:
                    msg = unpack_message(conn)
                    if msg is None:
                        print('\n[!] Server closed the connection.')
                        return
                    print(f'\r[Server] {msg}')
                    sys.stdout.write('you> ')
                    sys.stdout.flush()

                elif src is sys.stdin:
                    line = sys.stdin.readline()
                    if not line:
                        continue
                    cmd = line.strip()
                    if not cmd:
                        continue

                    if cmd in ('/exit', '/quit'):
                        print('Disconnecting...')
                        return

                    tokens = cmd.split()
                    verb = tokens[0]

                    if verb == '/list':
                        conn.sendall(pack_message(cmd))
                        result = unpack_message(conn)
                        print(f'[Files on server]\n{result}\n')

                    elif verb == '/upload' and len(tokens) > 1:
                        path = tokens[1]
                        if not os.path.isfile(path):
                            print(f'[!] Local file not found: {path}\n')
                            continue
                        conn.sendall(pack_message(cmd))
                        print(f'Uploading {path}...')
                        upload_file(conn, path)
                        reply = unpack_message(conn)
                        print(f'[Server] {reply}\n')

                    elif verb == '/download' and len(tokens) > 1:
                        filename = tokens[1]
                        conn.sendall(pack_message(cmd))
                        status = unpack_message(conn)
                        if status == 'OK':
                            dest = os.path.join(STORAGE_DIR, os.path.basename(filename))
                            print(f'Downloading to {dest}...')
                            download_file(conn, dest)
                            print(f'[✓] Saved to {dest}\n')
                        else:
                            print(f'[Server] {status}\n')

                    else:
                        print('[!] Unknown command or missing argument.')
                        print('    Try /list, /upload <path>, or /download <name>\n')

    except KeyboardInterrupt:
        print('\nInterrupted.')
    except Exception as err:
        print(f'\n[!] Error: {err}')
    finally:
        conn.close()


if __name__ == '__main__':
    run_client()