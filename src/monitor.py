import threading
import queue
import cv2
import numpy as np
import requests

ESP32_CAM_IP = "10.231.207.112"
STREAM_URL = f"http://{ESP32_CAM_IP}:81/stream"
CHUNK_SIZE = 8192


def reader_loop(stop_event: threading.Event, latest: queue.Queue):
    while not stop_event.is_set():
        try:
            r = requests.get(STREAM_URL, stream=True, timeout=5)
        except requests.exceptions.RequestException as e:
            print(f"Erro de conexão: {e} — tentando novamente em 2s")
            stop_event.wait(2)
            continue

        if r.status_code != 200:
            print(f"Erro HTTP {r.status_code}")
            stop_event.wait(2)
            continue

        print("Conectado ao stream.")
        buffer = bytearray()
        try:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                if stop_event.is_set():
                    break
                buffer.extend(chunk)

                latest_jpg = None
                while True:
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9", start + 2) if start != -1 else -1
                    if start == -1 or end == -1:
                        break
                    latest_jpg = bytes(buffer[start:end + 2])
                    del buffer[:end + 2]

                if latest_jpg is None:
                    continue

                try:
                    latest.get_nowait()
                except queue.Empty:
                    pass
                latest.put(latest_jpg)
        except requests.exceptions.RequestException as e:
            print(f"Stream caiu: {e} — reconectando")
        finally:
            r.close()


def main():
    print(f"Conectando em {STREAM_URL}...")
    stop_event = threading.Event()
    latest = queue.Queue(maxsize=1)

    t = threading.Thread(target=reader_loop, args=(stop_event, latest), daemon=True)
    t.start()

    print("Pressione 'q' na janela para sair.")
    try:
        while True:
            try:
                jpg = latest.get(timeout=0.5)
            except queue.Empty:
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue

            cv2.imshow("ESP32-CAM Stream", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        stop_event.set()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
