[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/mRmkZGKe)
# Network Programming - Assignment G01

## Anggota Kelompok
| Nama           | NRP        | Kelas     |
| ---            | ---        | ----------|
| Hisyam Syafa Raditya | 5025241130 | D |
| A. Wildan Kevin Assyauqi | 5025241265 | D |

## Link Youtube (Unlisted)
Link ditaruh di bawah ini
```

```

## Penjelasan Program
Proyek ini merupakan implementasi sistem transfer file berbasis protokol TCP menggunakan arsitektur Client-Server. Tujuan utama proyek ini adalah mempelajari cara kerja pengiriman dan penerimaan data melalui jaringan, sekaligus membandingkan berbagai pendekatan penanganan koneksi klien secara bersamaan dalam bahasa Python.

**Cara Kerja Umum:**
- **Client** terhubung ke server TCP pada alamat `localhost` port `9090`.
- Setiap data yang dikirim melalui jaringan — baik pesan teks maupun potongan file — menggunakan format _length-prefixed framing_, yaitu 4 byte di awal yang menyatakan panjang data, diikuti oleh data sebenarnya. Dengan cara ini, penerima mengetahui berapa byte yang harus dibaca.
- Client menyediakan prompt interaktif yang menerima perintah: `/list`, `/upload`, `/download`, dan `/exit`.
- Server memproses perintah tersebut, menyimpan file yang diunggah ke folder `server_storage`, dan pada implementasi selain _sync_ juga mengirimkan notifikasi (_broadcast_) ke seluruh klien yang sedang terhubung.

---

### Penjelasan Program Client (`client.py`)
Program `client.py` berfungsi sebagai antarmuka antara pengguna dan server. Client menggunakan `select.select()` di dalam loop utamanya untuk memantau dua sumber input secara non-blocking sekaligus: masukan dari keyboard (`sys.stdin`) dan pesan yang masuk dari server (`conn`).

**Daftar Fungsi Klien:**

- **`pack_message(text)`**
  Mengubah string menjadi bytes (UTF-8) dan menambahkan prefix 4 byte yang berisi panjang string tersebut.
  ```python
  def pack_message(text):
      encoded = text.encode('utf-8')
      return struct.pack('>I', len(encoded)) + encoded
  ```

- **`unpack_message(sock)`**
  Membaca 4 byte header terlebih dahulu untuk mengetahui panjang pesan, kemudian memanggil `_recv_exact` untuk mengambil isi pesannya.
  ```python
  def unpack_message(sock):
      raw_len = _recv_exact(sock, 4)
      if not raw_len:
          return None
      msg_len = struct.unpack('>I', raw_len)[0]
      data = _recv_exact(sock, msg_len)
      return data.decode('utf-8') if data else None
  ```

- **`_recv_exact(sock, n)`**
  Melakukan perulangan `sock.recv()` hingga tepat `n` byte terkumpul. Fungsi ini diperlukan karena TCP dapat mengirimkan data secara sebagian-sebagian (_partial read_).
  ```python
  def _recv_exact(sock, n):
      buffer = b''
      while len(buffer) < n:
          piece = sock.recv(n - len(buffer))
          if not piece:
              return None
          buffer += piece
      return buffer
  ```

- **`upload_file(sock, local_path)`**
  Membuka file lokal dan mengirimkan isinya ke server per potongan (_chunk_ 4096 byte). Setiap chunk dikirim dengan header ukurannya. Setelah file habis, dikirimkan paket 4 byte bernilai `0` sebagai penanda akhir.
  ```python
  def upload_file(sock, local_path):
      with open(local_path, 'rb') as fh:
          while True:
              chunk = fh.read(CHUNK_SIZE)
              if not chunk:
                  break
              sock.sendall(struct.pack('>I', len(chunk)) + chunk)
      sock.sendall(struct.pack('>I', 0))
  ```

- **`download_file(sock, save_path)`**
  Menerima chunk dari server satu per satu hingga ditemukan header bernilai `0`, lalu menyimpan hasilnya ke `save_path` di sisi client.
  ```python
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
  ```

---

### Penjelasan Program Server secara General
Server mendengarkan koneksi masuk pada port `9090`. Seluruh implementasi server dalam proyek ini memiliki perilaku dasar yang sama:
- Menggunakan flag `SO_REUSEADDR` agar port dapat langsung dipakai kembali saat server di-restart.
- Menerima perintah dari client dan membalas dengan status operasi, atau menjalankan proses transfer file jika perintah yang diterima adalah `/upload` atau `/download`.
- Menyimpan seluruh file yang diunggah klien ke dalam folder `server_storage`.

---

### Fungsi Server yang Digunakan di Semua Jenis
Karena seluruh implementasi server memiliki tugas dasar yang serupa, terdapat sejumlah fungsi utilitas yang hampir identik pada setiap varian (`-sync`, `-thread`, `-select`, `-poll`):

- **`send_text(sock, text)`**
  Mengirimkan pesan teks ke client, baik berupa balasan `OK`, pesan error, maupun notifikasi broadcast.
  ```python
  def send_text(sock, text):
      data = text.encode('utf-8')
      sock.sendall(struct.pack('>I', len(data)) + data)
  ```

- **`recv_text(sock)`**
  Sama seperti `unpack_message` di sisi client — membaca 4 byte header terlebih dahulu, kemudian mengambil isi pesan.
  ```python
  def recv_text(sock):
      hdr = _recv_exact(sock, 4)
      if not hdr:
          return None
      length = struct.unpack('>I', hdr)[0]
      body = _recv_exact(sock, length)
      return body.decode('utf-8') if body else None
  ```

- **`receive_file(sock, dest_path)` & `send_file(sock, src_path)`**
  Fungsi untuk melakukan streaming file di sisi server. Menggunakan perulangan per chunk sehingga file berukuran besar sekalipun tetap aman di memori tanpa perlu dimuat seluruhnya sekaligus.
  ```python
  def receive_file(sock, dest_path):
      with open(dest_path, 'wb') as fh:
          while True:
              hdr = _recv_exact(sock, 4)
              if not hdr: break
              length = struct.unpack('>I', hdr)[0]
              if length == 0: break
              chunk = _recv_exact(sock, length)
              if not chunk: break
              fh.write(chunk)

  def send_file(sock, src_path):
      with open(src_path, 'rb') as fh:
          while True:
              chunk = fh.read(CHUNK)
              if not chunk: break
              sock.sendall(struct.pack('>I', len(chunk)) + chunk)
      sock.sendall(struct.pack('>I', 0))
  ```

- **`sanitize(raw_name, sock, addr)`**
  Fungsi keamanan dasar untuk mencegah serangan _directory traversal_. Jika client mengirimkan nama file seperti `../../etc/passwd`, fungsi ini akan memotongnya menjadi nama file yang aman dan tetap tersimpan di dalam folder `server_storage`.
  ```python
  def sanitize(raw_name, sock, addr):
      name = os.path.basename(raw_name)
      if name in ('', '.', '..'):
          logging.warning(f'{addr} sent invalid filename: {raw_name!r}')
          send_text(sock, 'ERROR: invalid filename')
          return None
      return name
  ```

- **`broadcast(message, ...)`**
  *(Hanya tersedia pada implementasi non-sync)*
  Mengirimkan pesan notifikasi ke seluruh client yang sedang terhubung, kecuali pengirimnya sendiri.
  ```python
  # Contoh implementasi pada select/poll
  def broadcast(message, sender_sock, client_map):
      for fd, info in client_map.items():
          if info['sock'] is not sender_sock:
              try:
                  send_text(info['sock'], f'[broadcast] {message}')
              except Exception:
                  pass
  ```

---

### Penjelasan Tiap Server dan Cara Kerja Masing-Masing
Proyek ini memiliki empat varian server dengan pendekatan yang berbeda-beda dalam menangani koneksi klien secara bersamaan.

---

#### A. Server Synchronous (`server-sync.py`)

**Cara Kerja:**
Merupakan implementasi paling dasar dari seluruh varian server. Server hanya mampu melayani satu klien dalam satu waktu secara penuh. Setelah koneksi diterima melalui `srv.accept()`, thread utama akan terkunci di dalam loop perintah klien tersebut hingga koneksi terputus. Klien berikutnya baru dapat masuk setelah klien sebelumnya selesai.

**Alur `main()`:**
```python
def main():
    os.makedirs(STORAGE, exist_ok=True)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)

    while True:
        conn, addr = srv.accept()                          # Menunggu koneksi baru
        send_text(conn, 'Welcome! Connected to sync server.')
        try:
            while True:
                cmd = recv_text(conn)                      # Blocking — menunggu perintah klien ini
                if cmd is None:
                    break
                handle_command(cmd, conn, addr)
        finally:
            conn.close()                                   # Baru setelah ini klien berikutnya dapat masuk
```

**Fungsi `handle_command(cmd, sock, addr)`:**
Memproses setiap perintah yang dikirim klien. Terdapat tiga perintah yang didukung:
- `/list` → Membaca isi folder `server_storage` dengan `os.listdir()` dan mengirimkan daftarnya sebagai teks.
- `/upload <nama_file>` → Memanggil `sanitize()` untuk validasi nama file, lalu `receive_file()` untuk menerima data, kemudian membalas dengan konfirmasi `'Upload complete: <nama_file>'`.
- `/download <nama_file>` → Memeriksa keberadaan file di `server_storage`. Jika ada, mengirim `'OK'` terlebih dahulu lalu memanggil `send_file()`. Jika tidak ada, mengirimkan pesan error.

```python
def handle_command(cmd, sock, addr):
    parts = cmd.split()
    verb = parts[0] if parts else ''

    if verb == '/list':
        files = os.listdir(STORAGE)
        payload = '\n'.join(files) if files else '(no files on server)'
        send_text(sock, payload)

    elif verb == '/upload' and len(parts) > 1:
        name = sanitize(parts[1], sock, addr)
        if not name: return
        dest = os.path.join(STORAGE, name)
        receive_file(sock, dest)
        send_text(sock, f'Upload complete: {name}')

    elif verb == '/download' and len(parts) > 1:
        name = sanitize(parts[1], sock, addr)
        if not name: return
        path = os.path.join(STORAGE, name)
        if not os.path.isfile(path):
            send_text(sock, f'ERROR: {name} not found on server')
            return
        send_text(sock, 'OK')
        send_file(sock, path)
```

**Keterbatasan:** Tidak mendukung konkurensi. Cocok hanya untuk pengujian dasar atau skenario single-user.

---

#### B. Server Multi-threaded (`server-thread.py`)

**Cara Kerja:**
Setiap klien yang terhubung dijalankan di dalam `threading.Thread` tersendiri (daemon thread). Thread utama hanya bertugas menerima koneksi baru melalui `accept()` dan mendelegasikan penanganannya ke objek `ClientHandler`. Semua klien aktif dilacak dalam list global `connected_clients` yang dilindungi oleh `registry_lock`.

**Variabel Global:**
```python
registry_lock = threading.Lock()
connected_clients: list = []
```
`registry_lock` digunakan setiap kali `connected_clients` dimodifikasi untuk mencegah _race condition_ saat beberapa thread mengakses list secara bersamaan.

**Alur `main()`:**
```python
def main():
    server_sock.listen(10)
    while True:
        conn, addr = server_sock.accept()
        handler = ClientHandler(conn, addr)
        with registry_lock:
            connected_clients.append(handler)     # Daftarkan ke registry
        handler.start()                           # Jalankan di thread terpisah
        send_text(conn, 'Welcome! Connected to threaded server.')
        broadcast(f'New client joined: {addr}', exclude=handler)
```

**Kelas `ClientHandler(threading.Thread)`:**
Setiap klien direpresentasikan sebagai objek `ClientHandler` yang mewarisi `threading.Thread`. Method `run()` adalah titik masuk eksekusi thread:
```python
def run(self):
    try:
        while True:
            cmd = recv_text(self.sock)
            if cmd is None:
                break
            self._handle(cmd)
    except (ConnectionResetError, BrokenPipeError, OSError) as ex:
        logging.warning(f'{self.addr} connection lost: {ex}')
    finally:
        self._cleanup()
```

**Method `_cleanup()`:**
Dipanggil otomatis saat thread selesai (klien disconnect). Menghapus handler dari `connected_clients`, menutup socket, lalu melakukan broadcast bahwa klien telah keluar.
```python
def _cleanup(self):
    with registry_lock:
        if self in connected_clients:
            connected_clients.remove(self)
    self.sock.close()
    broadcast(f'Client {self.addr} has left.', exclude=self)
```

**Fungsi `broadcast(message, exclude=None)`:**
Mengambil salinan list klien aktif di bawah lock, lalu mengirim pesan ke semua klien kecuali yang dikecualikan.
```python
def broadcast(message, exclude=None):
    with registry_lock:
        targets = [c for c in connected_clients if c is not exclude]
    for client in targets:
        try:
            client.write(f'[broadcast] {message}')
        except Exception:
            pass
```

**Kelebihan:** Mendukung banyak klien secara paralel sejati. **Keterbatasan:** Setiap klien mengonsumsi satu thread OS, sehingga kurang efisien untuk jumlah koneksi yang sangat besar.

---

#### C. Server Berbasis Select (`server-select.py`)

**Cara Kerja:**
Menggunakan mekanisme I/O multiplexing melalui pemanggilan sistem `select.select()`. Server tidak menggunakan thread tambahan — seluruh koneksi dipantau dari satu thread menggunakan dua struktur data: `watch` (list socket yang dipantau) dan `client_map` (dictionary berisi info tiap klien berindeks `fileno()`).

**Struktur Data:**
```python
watch = [server_sock]     # List socket yang dipantau oleh select()
client_map = {}           # { fd: {'sock': conn, 'addr': addr} }
```

**Alur Event Loop `main()`:**
```python
while True:
    readable, _, exceptional = select.select(watch, [], watch, 1.0)

    for sock in readable:
        if sock is server_sock:
            # Ada koneksi baru masuk
            conn, addr = server_sock.accept()
            conn.setblocking(True)
            watch.append(conn)
            client_map[conn.fileno()] = {'sock': conn, 'addr': addr}
            send_text(conn, 'Welcome! Connected to select-based server.')
            broadcast(f'New client joined: {addr}', conn, client_map)
        else:
            # Ada data masuk dari klien yang sudah terhubung
            addr = client_map.get(sock.fileno(), {}).get('addr', '?')
            try:
                cmd = recv_text(sock)
                if cmd is None:
                    raise ConnectionResetError
                handle_command(cmd, sock, addr, client_map)
            except (ConnectionResetError, BrokenPipeError, OSError):
                broadcast(f'Client left: {addr}', sock, client_map)
                watch.remove(sock)
                client_map.pop(sock.fileno(), None)
                sock.close()

    for sock in exceptional:
        # Tangani socket yang mengalami error
        watch.remove(sock)
        client_map.pop(sock.fileno(), None)
        sock.close()
```

**Fungsi `broadcast(message, sender_sock, client_map)`:**
Iterasi melalui `client_map` dan kirim pesan ke semua socket kecuali pengirimnya sendiri.
```python
def broadcast(message, sender_sock, client_map):
    for fd, info in client_map.items():
        if info['sock'] is not sender_sock:
            try:
                send_text(info['sock'], f'[broadcast] {message}')
            except Exception:
                pass
```

`handle_command()` pada implementasi ini mendapat parameter tambahan `client_map` agar dapat memanggil `broadcast()` saat ada operasi upload.

**Keterbatasan:** `select()` memiliki batas maksimum file descriptor yang dapat dipantau dalam sekali pemanggilan (umumnya 1024 pada sistem POSIX), sehingga tidak cocok untuk skala yang sangat besar.

---

#### D. Server Berbasis Poll (`server-poll.py`)

**Cara Kerja:**
Merupakan evolusi dari `select`. Alih-alih melempar ulang seluruh list socket ke kernel pada setiap iterasi, `poll` menggunakan objek `poller` yang menyimpan registrasi file descriptor secara persisten. Socket baru didaftarkan dengan `poller.register()` dan socket yang disconnect di-unregister dengan `poller.unregister()`.

**Konstanta Event:**
```python
POLL_IN  = select.POLLIN  | select.POLLPRI    # Ada data yang siap dibaca
POLL_ERR = select.POLLERR | select.POLLHUP | select.POLLNVAL  # Error / koneksi terputus
```

**Struktur Data:**
```python
fd_map = {}   # { fd: {'sock': conn, 'addr': addr} }
```
Berbeda dengan `select` yang menggunakan `watch` (list), `poll` menggunakan `fd_map` (dictionary) sehingga pencarian informasi klien berdasarkan `fd` berjalan dalam O(1).

**Alur Event Loop `main()`:**
```python
poller = select.poll()
poller.register(server_fd, POLL_IN)

while True:
    events = poller.poll(1000)   # Timeout 1 detik, mengembalikan list (fd, event)

    for fd, event in events:
        if event & POLL_ERR:
            if fd == server_fd:
                raise RuntimeError('Error on server socket')
            addr = remove_client(fd, poller, fd_map)
            broadcast(f'Client {addr} dropped (error)', fd, fd_map)
            continue

        if fd == server_fd:
            # Koneksi baru masuk
            conn, addr = server_sock.accept()
            conn.setblocking(True)
            cfd = conn.fileno()
            fd_map[cfd] = {'sock': conn, 'addr': addr}
            poller.register(cfd, POLL_IN)          # Daftarkan ke poller
            send_text(conn, 'Welcome! Connected to poll-based server.')
            broadcast(f'New client: {addr}', cfd, fd_map)
        else:
            # Data masuk dari klien yang sudah terhubung
            info = fd_map.get(fd)
            if not info: continue
            sock, addr = info['sock'], info['addr']
            try:
                cmd = recv_text(sock)
                if cmd is None:
                    raise ConnectionResetError
                handle_command(cmd, sock, addr, fd, fd_map)
            except (ConnectionResetError, BrokenPipeError, OSError):
                remove_client(fd, poller, fd_map)
                broadcast(f'Client {addr} left', fd, fd_map)
```

**Fungsi `remove_client(fd, poller, fd_map)`:**
Fungsi khusus yang menggabungkan proses unregister dari poller, penghapusan dari `fd_map`, dan penutupan socket menjadi satu langkah.
```python
def remove_client(fd, poller, fd_map):
    info = fd_map.pop(fd, None)
    poller.unregister(fd)
    if info:
        addr = info['addr']
        info['sock'].close()
        return addr
    return fd
```

`handle_command()` pada implementasi ini menerima parameter `fd` dan `fd_map` (selain `sock`) karena `broadcast()` membutuhkan `fd` pengirim untuk mengecualikannya dari pengiriman notifikasi.

**Kelebihan dibanding Select:** Tidak ada batasan hard-limit jumlah file descriptor, overhead pengiriman data ke kernel lebih kecil karena registrasi bersifat persisten, serta penanganan error lebih granular melalui flag `POLL_ERR`, `POLLHUP`, dan `POLLNVAL`.

## Screenshot Hasil