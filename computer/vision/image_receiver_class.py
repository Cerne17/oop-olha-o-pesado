import cv2
import time
from computer.types.observers import FrameObservable
from computer.types.signals import Frame

class ImageReceiver(FrameObservable):
    def __init__(self):
        # Inicializa a infraestrutura de avisos do FrameObservable
        super().__init__() 
        self.cap = cv2.VideoCapture(0)
        self.finish = False
        self.frame_id_counter = 0
    
    def Run(self):
        while self.cap.isOpened() and not self.finish:
            success, img = self.cap.read()
            if not success:
                continue
            
            img = cv2.resize(img, (640, 480)) # Usada para diminuir gasto computacional
            img = cv2.flip(img, 1)  # Inverter para efeito de espelho
            
            # --- ADAPTAÇÃO PARA A CAIXA PRETA ---
            # A sua nova ComputerVision espera um 'Frame' contendo o JPEG em bytes
            # Então nós codificamos a imagem do OpenCV para JPEG aqui:
            success_encode, buffer = cv2.imencode('.jpg', img)
            
            if success_encode:
                jpeg_bytes = buffer.tobytes()
                
                # Monta o pacote oficial
                frame_oficial = Frame(
                    frame_id=self.frame_id_counter,
                    jpeg=jpeg_bytes,
                    timestamp=time.monotonic()
                )
                self.frame_id_counter += 1
                
                # Avisa todos os interessados (a sua ComputerVision) que a foto está pronta
                self._notify_frame(frame_oficial)
            
            # Pequeno delay para simular a taxa de quadros (FPS) da câmera Bluetooth real
            time.sleep(0.05) 
            
        self.CloseImages()
    
    def CloseImages(self):
        if self.cap is not None:
            self.cap.release()
        cv2.destroyAllWindows()
    
    def Finish(self):
        self.finish = True