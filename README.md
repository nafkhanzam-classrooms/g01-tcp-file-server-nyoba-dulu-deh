# Dokumentasi Proyek: TCP File Transfer Server

## 1. Tujuan dan Cara Kerja Project
Proyek ini merupakan implementasi sistem transfer file berbasis protokol TCP menggunakan arsitektur Client-Server. Tujuan utama proyek ini adalah mempelajari cara kerja pengiriman dan penerimaan data melalui jaringan, sekaligus membandingkan berbagai pendekatan penanganan koneksi klien secara bersamaan dalam bahasa Python.

**Cara Kerja Umum:**
- **Client** terhubung ke server TCP pada alamat `localhost` port `9090`.
- Setiap data yang dikirim melalui jaringan — baik pesan teks maupun potongan file — menggunakan format _length-prefixed framing_, yaitu 4 byte di awal yang menyatakan panjang data, diikuti oleh data sebenarnya. Dengan cara ini, penerima mengetahui berapa byte yang harus dibaca.
- Client menyediakan prompt interaktif yang menerima perintah: `/list`, `/upload`, `/download`, dan `/exit`.
- Server memproses perintah tersebut, menyimpan file yang diunggah ke folder `server_storage`, dan pada implementasi selain _sync_ juga mengirimkan notifikasi (_broadcast_) ke seluruh klien yang sedang terhubung.

---

## 2. Penjelasan Program Client (`client.py`)
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

## 3. Penjelasan Program Server secara General
Server mendengarkan koneksi masuk pada port `9090`. Seluruh implementasi server dalam proyek ini memiliki perilaku dasar yang sama:
- Menggunakan flag `SO_REUSEADDR` agar port dapat langsung dipakai kembali saat server di-restart.
- Menerima perintah dari client dan membalas dengan status operasi, atau menjalankan proses transfer file jika perintah yang diterima adalah `/upload` atau `/download`.
- Menyimpan seluruh file yang diunggah klien ke dalam folder `server_storage`.

---

## 4. Fungsi Server yang Sama di Semua Jenis
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

## 5. Penjelasan Tiap Server dan Cara Kerja Masing-Masing
Proyek ini memiliki empat varian server dengan pendekatan yang berbeda-beda:

### A. Server Synchronous (`server-sync.py`)
- **Cara Kerja:** Merupakan versi paling dasar. Server menerima koneksi satu per satu — setelah ada client yang terhubung melalui `srv.accept()`, thread utama akan sepenuhnya melayani client tersebut hingga disconnect. Client lain harus menunggu dalam antrian.
- **Karakteristik Kode:**
  Eksekusinya bersifat sekuensial murni; client berikutnya baru dilayani setelah client sebelumnya selesai.
  ```python
  while True:
      conn, addr = srv.accept()
      # Tertahan di sini sampai client ini selesai
      while True:
          cmd = recv_text(conn)
          if cmd is None: break
  ```

### B. Server Multi-threaded (`server-thread.py`)
- **Cara Kerja:** Dibuat untuk mengatasi keterbatasan server synchronous. Thread utama hanya bertugas menerima koneksi baru. Setiap client yang masuk dilempar ke thread baru (daemon thread) sehingga dapat berjalan secara paralel.
- **Karakteristik Kode:**
  Menggunakan `registry_lock` agar penambahan ke list `connected_clients` aman dari _race condition_.
  ```python
  conn, addr = server_sock.accept()
  handler = ClientHandler(conn, addr)
  with registry_lock:
      connected_clients.append(handler)
  handler.start()  # Berjalan di thread sendiri
  ```

### C. Server Berbasis Select (`server-select.py`)
- **Cara Kerja:** Implementasi event-driven single-thread menggunakan `select()` dari POSIX. Server memasukkan seluruh socket (server dan semua client) ke dalam `watch_list`, lalu menyerahkannya ke kernel. Kernel yang akan memberitahu socket mana yang siap untuk dibaca.
- **Karakteristik Kode:**
  Jumlah file descriptor yang dapat dipantau terbatas — umumnya maksimal 1024 pada kebanyakan sistem operasi.
  ```python
  watch = [server_sock]
  while True:
      readable, _, exceptional = select.select(watch, [], watch, 1.0)
      for sock in readable:
          if sock is server_sock:
              # Client baru masuk
          else:
              # Terima perintah dari client yang sudah terhubung
  ```

### D. Server Berbasis Poll (`server-poll.py`)
- **Cara Kerja:** Merupakan peningkatan dari select — tidak memiliki batasan jumlah file descriptor. Berbeda dengan select yang melempar ulang seluruh array setiap iterasi, poll menggunakan pendaftaran file descriptor secara dinamis. Client baru langsung didaftarkan, dan client yang disconnect langsung di-unregister.
- **Karakteristik Kode:**
  Pengecekan dilakukan melalui hash table `fd_map` dengan akses O(1), sehingga lebih efisien untuk jumlah client yang besar.
  ```python
  poller = select.poll()
  poller.register(server_fd, POLL_IN)
  while True:
      events = poller.poll(1000)  # Menunggu event dari OS
      for fd, event in events:
          if event & POLL_ERR:
             # Handle error
          if fd == server_fd:
             # Handle koneksi baru, lalu register socket barunya ke poller
  ```
