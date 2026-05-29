import time
import requests
from computer.types.observers import FrameObservable
from computer.types.signals import Frame

ESP32_CAM_IP = "10.231.207.112"
STREAM_URL = f"http://{ESP32_CAM_IP}:81/stream"
CHUNK_SIZE = 8192

class ImageReceiver(FrameObservable):
    def __init__(self):
        super().__init__()
        self.finish = False
        self.frame_id_counter = 0

    def Run(self):
        print(f"[RECEIVER] Conectando ao ESP32-CAM em {STREAM_URL}...")

        while not self.finish:
            try:
                # Inicia a conexão com o fluxo de vídeo da ESP32
                r = requests.get(STREAM_URL, stream=True, timeout=5)
            except requests.exceptions.RequestException as e:
                print(f"[RECEIVER] Erro de conexão: {e} — tentando novamente em 2s")
                time.sleep(2)
                continue

            if r.status_code != 200:
                print(f"[RECEIVER] Erro HTTP {r.status_code} recebido.")
                time.sleep(2)
                continue

            print("[RECEIVER] Conectado ao stream com sucesso!")
            buffer = bytearray()

            try:
                # Começa a baixar os dados em pedaços (chunks)
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if self.finish:
                        break
                    
                    buffer.extend(chunk)

                    # Procura os marcadores hexadecimais de começo e fim de um frame JPEG
                    while True:
                        start = buffer.find(b"\xff\xd8")
                        end = buffer.find(b"\xff\xd9", start + 2) if start != -1 else -1

                        if start == -1 or end == -1:
                            break # O frame ainda está incompleto, pega mais chunks

                        # Extrai a imagem completa em bytes
                        latest_jpg = bytes(buffer[start:end + 2])
                        del buffer[:end + 2] # Limpa o buffer até o final desse frame recém extraído

                        # Monta o pacote oficial do sistema
                        frame_oficial = Frame(
                            frame_id=self.frame_id_counter,
                            jpeg=latest_jpg,
                            timestamp=time.monotonic()
                        )
                        self.frame_id_counter += 1

                        # Avisa os observadores (ComputerVision) que há uma foto nova
                        self._notify_frame(frame_oficial)

            except requests.exceptions.RequestException as e:
                print(f"[RECEIVER] Stream caiu: {e} — reconectando...")
            finally:
                r.close()

        self.CloseImages()

    def CloseImages(self):
        # Apenas mantido por compatibilidade de estrutura, 
        # já que a liberação de porta USB (cap.release) não existe mais.
        pass

    def Finish(self):
        self.finish = True