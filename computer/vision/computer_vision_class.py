import cv2
import mediapipe as mp
import threading

from detection_utils import process_image, identify_gesture, init_person_detector, detect_persons, get_matching_person
from image_utils import write_gesture_name, draw_squeleton, draw_person_box

#########################################################
# Inicialização do MediaPipe
#########################################################

BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

def hand_landmarker_options():
    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path='hand_landmarker.task'),
        running_mode=VisionRunningMode.LIVE_STREAM,
        num_hands=5,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.5,
        result_callback=result_callback
    )
    return options


#########################################################
# Lógica para mediapipe operar de forma assíncrona e não travar recebimento de imagens
#########################################################

# Variável global para armazenar o resultado do processamento assíncrono
latest_result = None

def result_callback(result, output_image, timestamp_ms):
    global latest_result
    latest_result = result

#########################################################
# Computer Vision Class
#########################################################

class ComputerVision():
    def __init__(self, receiver):
        # Inicializa Modelos do MediaPipe e da Yolo-pose
        self.options = hand_landmarker_options()
        self.detector_model = init_person_detector()

        # Inicializa atributos
        self.image_event = threading.Event()
        self.finish = False
        self.receiver = receiver
        self.timestamp = 0

        # Variaveis de Rastreamento da Máquina de Estados
        self.alvo_rastreado_id = None
        self.frames_perdido = 0 # Contador de frames sem ver o mestre
        self.limite_frames_perdido = 10 # Se sumir por 10 frames, reseta!
    
    def Run(self):
        """Coordena execução do programa."""
        with HandLandmarker.create_from_options(self.options) as self.landmarker:
            while not self.finish:
                self.WaitImage()
                img, img_rgb = self.receiver.GetImage()
                ref = self.ProcessImage(img=img, img_rgb=img_rgb)
                self.SendRef(ref=ref)
            self.receiver.Finish()

    def WaitImage(self):
        """Espera por uma imagem estar pronta para ser processada"""
        # O código congela nesta linha até o sinal ser dado para prosseguir
        self.image_event.wait()
    
    def NotifyNewImage(self):
        """Informa que há nova imagem pronta."""
        self.image_event.set()
    
    def ProcessImage(self, img, img_rgb):

        ref = 0 # apenas para testes iniciais

        # 1. Fecha o semáforo novamente para aguardar o próximo frame
        self.image_event.clear()
        
        # 2. Processa a imagem
        process_image(self.landmarker, img_rgb, self.timestamp)
        self.timestamp += 1

        # 3 Detecta pessoas na imagem
        persons_data = detect_persons(self.detector_model, img)

        # Usamos um dicionário para ligar a pessoa ao gesto -> {id: gesto}
        gestos_das_pessoas = {}

        # 4. Analisa os resultados se estiverem disponíveis
        # Associa os Gestos aos IDs das Pessoas
        if latest_result and latest_result.hand_landmarks:
            for hand_lms in latest_result.hand_landmarks:

                # 4.1 Identifica o gesto desta mão
                gesto_atual = identify_gesture(hand_lms)

                # 4.2 Descobre de quem é esta mão pela menor distância
                pessoa_dono = get_matching_person(hand_lms, persons_data, img)

                # Se encontrou um dono válido (mão acima do ombro e calculada)
                if pessoa_dono is not None:
                    p_id = pessoa_dono["id"]

                    # Ignora se for o frame 1 e a pessoa ainda tiver o RG provisório (-1)
                    if p_id != -1:

                        if p_id not in gestos_das_pessoas:
                            gestos_das_pessoas[p_id] = []

                        # Só atualiza o dicionário se a mão atual estiver fazendo um gesto válido
                        if gesto_atual != "NENHUM":
                            gestos_das_pessoas[p_id].append(gesto_atual)

                # 4.3 Desenhos visuais (esqueleto)
                img = draw_squeleton(img, hand_lms)
        
        # 5 MÁQUINA DE ESTADOS: Buscar ou Seguir
        mestre_visto_agora = False # Variável para saber se vimos o mestre NESTE frame

        for person in persons_data:
            p_id = person["id"]
            bbox = person["box"]

            # Pega o gesto dessa pessoa específica (se não estiver no dicionário, retorna "NENHUM")
            gestos_dessa_pessoa = gestos_das_pessoas.get(p_id, [])

            # ESTADO 1: Procurando um mestre (alvo_rastreado_id é None)
            if self.alvo_rastreado_id is None:
                # O robô está livre. Se alguém fizer um duplo ROCK, vira o alvo!
                if gestos_dessa_pessoa.count("ROCK") == 2: 
                    self.alvo_rastreado_id = p_id
                    print(f"Alvo TRAVADO! Seguindo a pessoa de ID: {p_id}")
                    
                # Desenha como neutro (vermelho) enquanto não acha ninguém
                img = draw_person_box(img, bbox, False) 
            
            # ESTADO 2: Focado no mestre
            elif p_id == self.alvo_rastreado_id:
                # ESTE É O MESTRE! 

                mestre_visto_agora = True
                self.frames_perdido = 0

                # Aqui você pode calcular a ref! (ex: posição X do centro da caixa)
                centro_x = (bbox[0] + bbox[2]) // 2
                ref = centro_x 
                    
                # Desenha a caixa verde e foca o texto nele
                img = draw_person_box(img, bbox, True) 

                # Condição de Cancelamento: Mestre faz um duplo ROCK
                if gestos_dessa_pessoa.count("ROCK") == 1 and gestos_dessa_pessoa.count("STOP") == 1:
                    self.alvo_rastreado_id = None
                    print("Alvo cancelado pelo gesto. Voltando ao modo de busca.")
        
        # 6. GATILHO DE PERDA DO ALVO (TIMEOUT)
        # Se temos um alvo registrado, mas ele não apareceu no laço acima...
        if self.alvo_rastreado_id is not None and not mestre_visto_agora:
            self.frames_perdido += 1
            
            # Se sumiu por muito tempo, reseta a máquina de estados
            if self.frames_perdido > self.limite_frames_perdido:
                print("Alvo saiu da tela por muito tempo! Resetando...")
                self.alvo_rastreado_id = None
                self.frames_perdido = 0
                ref = 0 # Para o robô

        # 7. Cria janela com imagem em tempo real
        cv2.imshow("Detector de Gestos", img)

        # Encerra se usuário apertar 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            self.finish = True
        
        return ref

    def SendRef(self,ref):
        pass