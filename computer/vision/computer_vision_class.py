import cv2
import mediapipe as mp
import threading
import numpy as np
import time

from computer.types.observers import FrameObserver, ControlObservable
from computer.types.signals import Frame, ControlSignal

from computer.vision.detection_utils import process_image, identify_gesture, init_person_detector, detect_persons, get_matching_person
from computer.vision.image_utils import write_gesture_name, draw_squeleton, draw_person_box

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

class ComputerVision(FrameObserver, ControlObservable):
    def __init__(self):
        # Inicializa Classes Abstratas
        FrameObserver.__init__(self)
        ControlObservable.__init__(self)

        # Inicializa Modelos do MediaPipe e da Yolo-pose
        self.options = hand_landmarker_options()
        self.detector_model = init_person_detector()

        # Inicializa atributos
        self.image_event = threading.Event()
        self.finish = False
        self.timestamp = 0

        # Buffer para guardar o frame que o CamReceiver entregar
        self.latest_frame = None

        # Variaveis de Rastreamento da Máquina de Estados
        self.alvo_rastreado_id = None
        self.tempo_perda_alvo = None

        # Variáveis do Controle de Rastreamento
        self.tamanho_alvo_ref = None
        # Ajustar na pratica os valores abaixo
        self.kp_velocidade = 0.02 # ganho de velocidade v = (kp * dif_tamanho_tronco)
        self.angle_max = 90.0 # angulo caso alvo esteja na borda da imagem

    # -------------------------------------------------------------------------
    # INTERFACE DE ENTRADA: O sinalizador avisa por aqui quando há um novo frame
    # -------------------------------------------------------------------------
    def on_frame(self, frame: Frame) -> None:
        """
        Método obrigatório do FrameObserver.
        Chamado automaticamente pelo CamReceiver sempre que uma foto nova estiver pronta.
        """
        self.latest_frame = frame
        self.image_event.set() # Acorda a thread principal (Run) para processar

    def Run(self):
        """Coordena execução do programa na thread principal."""
        with HandLandmarker.create_from_options(self.options) as self.landmarker:
            while not self.finish:
                # Espera o on_frame sinalizar que chegou uma imagem
                self.image_event.wait()
                self.image_event.clear()

                if self.latest_frame is None:
                    continue

                # Traduz os bytes do JPEG de volta para o OpenCV
                img = cv2.imdecode(np.frombuffer(self.latest_frame.jpeg, np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    continue
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                # Executa a inteligência e obtém o ControlSignal correto
                sinal_de_controle = self.ProcessImage(img=img, img_rgb=img_rgb)

                # -------------------------------------------------------------------------
                # INTERFACE DE SAÍDA: Avisa o RobotSender que um comando deve ser enviado
                # -------------------------------------------------------------------------
                self._notify_control(sinal_de_controle)
    
    def ProcessImage(self, img, img_rgb):

        # Pegando as dimensões da imagem para os cálculos de navegação
        img_height, img_width, _ = img.shape
        centro_img_x = img_width / 2.0
        
        # --- LÓGICA DO TEMPORIZADOR DE PERDA (2 SEGUNDOS NO VERMELHO) ---
        if self.tempo_perda_alvo is not None:
            if time.time() - self.tempo_perda_alvo < 2.0:
                # Se ainda não passaram 2 segundos, FORÇA o robô a continuar no vermelho
                ref = ControlSignal.lost()
            else:
                # Passou os 2 segundos! Limpa o temporizador e volta a ficar amarelo
                self.tempo_perda_alvo = None
                ref = ControlSignal.waiting()
        else:
            # Comportamento padrão (livre e procurando)
            ref = ControlSignal.waiting()
        
        # 1. Processa a imagem
        process_image(self.landmarker, img_rgb, self.timestamp)
        self.timestamp += 1

        # 2. Detecta pessoas na imagem
        persons_data = detect_persons(self.detector_model, img)

        # Usamos um dicionário para ligar a pessoa ao gesto -> {id: gesto}
        gestos_das_pessoas = {}

        # 3. Analisa os resultados se estiverem disponíveis
        # Associa os Gestos aos IDs das Pessoas
        if latest_result and latest_result.hand_landmarks:
            for hand_lms in latest_result.hand_landmarks:

                # 3.1 Identifica o gesto desta mão
                gesto_atual = identify_gesture(hand_lms)

                # 3.2 Descobre de quem é esta mão pela menor distância
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

                # 3.3 Desenhos visuais (esqueleto)
                img = draw_squeleton(img, hand_lms)
        
        # 4. MÁQUINA DE ESTADOS: Buscar ou Seguir
        mestre_visto_agora = False # Variável para saber se vimos o mestre NESTE frame

        for person in persons_data:
            p_id = person["id"]
            bbox = person["box"]

            # Pega o gesto dessa pessoa específica (se não estiver no dicionário, retorna "NENHUM")
            gestos_dessa_pessoa = gestos_das_pessoas.get(p_id, [])

            # --- CÁLCULO DA ALTURA DO TRONCO ---
            # Extraindo as coordenadas Y (índice 1) dos ombros e quadris
            y_ombro_esq = person["l_shoulder"][1]
            y_ombro_dir = person["r_shoulder"][1]
            y_quadril_esq = person["l_hip"][1]
            y_quadril_dir = person["r_hip"][1]
            # faz a media das alturas (esquerda e direita)
            y_ombros_medio = (y_ombro_esq + y_ombro_dir) / 2.0
            y_quadris_medio = (y_quadril_esq + y_quadril_dir) / 2.0
            # Calcula altura do tronco para ser usada no controle de velocidade
            tamanho_tronco_atual = abs(y_quadris_medio - y_ombros_medio)

            # ESTADO 1: Procurando um mestre (alvo_rastreado_id é None)
            if self.alvo_rastreado_id is None:
                # O robô está livre. Se alguém fizer um duplo ROCK, vira o alvo!
                # Se o robô estiver dando aviso de alvo perdido, nao procura novo alvo.
                
                if self.tempo_perda_alvo is None and gestos_dessa_pessoa.count("ROCK") == 2: 
                    self.alvo_rastreado_id = p_id

                    # Salva referencia de altura do tronco no momento do travamento de alvo
                    self.tamanho_alvo_ref = tamanho_tronco_atual
                    
                    mestre_visto_agora = True
                    print(f"Alvo TRAVADO! Seguindo a pessoa de ID: {p_id}")
                    
                # Desenha como neutro (vermelho) enquanto não acha ninguém
                img = draw_person_box(img, bbox, False) 
            
            # ESTADO 2: Focado no mestre
            elif p_id == self.alvo_rastreado_id:
                # ESTE É O MESTRE! 

                mestre_visto_agora = True

                # --- CALCULO DO SINAL DE REFERENCIA ---
                # Angulo
                centro_bbox_x = (bbox[0] + bbox[2]) / 2.0
                erro_x = centro_bbox_x - centro_img_x
                limite_zona_morta_angulo = img_width * 0.05 # define limite de largura onde angulo permanece 0
                if abs(erro_x) <= limite_zona_morta_angulo:
                    # Pessoa está no meio, vai reto
                    angulo_calculado = 0.0
                else:
                    # Se erro_x > 0 (angulo > 0), direita. Se erro_x < 0, esquerda.
                    angulo_calculado = self.angle_max * ( erro_x / (img_width / 2.0) )

                # Velocidade (altura do tronco)
                erro_tamanho_tronco = self.tamanho_alvo_ref - tamanho_tronco_atual
                limite_zona_morta_velocidade = self.tamanho_alvo_ref * 0.1 # Ignora variações pequenas
                if abs(erro_tamanho_tronco) <= limite_zona_morta_velocidade:
                    velocidade_calculada = 0.0
                else:
                    # Aplica o Controle Proporcional
                    velocidade_calculada = self.kp_velocidade * erro_tamanho_tronco
                    # Garante velocidade dentro dos limites estabelecidos
                    velocidade_calculada = max(-1.0, min(1.0, velocidade_calculada))

                ref = ControlSignal.following(angle=angulo_calculado, speed=velocidade_calculada)
                    
                # Desenha a caixa verde e foca o texto nele
                img = draw_person_box(img, bbox, True) 

                # Condição de Cancelamento: Mestre faz um duplo ROCK
                if gestos_dessa_pessoa.count("ROCK") == 1 and gestos_dessa_pessoa.count("STOP") == 1:
                    self.alvo_rastreado_id = None
                    self.tamanho_alvo_ref = None # Limpa a referência de tamanho do alvo
                    print("Alvo cancelado pelo gesto. Voltando ao modo de busca.")
                    ref = ControlSignal.waiting()
        
        # 5. GATILHO DE PERDA DO ALVO (TIMEOUT)
        # Se temos um alvo registrado, mas ele não apareceu no laço acima...
        if self.alvo_rastreado_id is not None and not mestre_visto_agora:
            print("Alvo perdido! Acionando estado LOST por 2 segundos.")
            self.alvo_rastreado_id = None
            self.tamanho_alvo_ref = None
            self.tempo_perda_alvo = time.time() # Dispara o cronômetro
            ref = ControlSignal.lost() # Para o robô

        # 6. Cria janela com imagem em tempo real
        cv2.imshow("Detector de Gestos", img)

        # Encerra se usuário apertar 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            self.finish = True
        
        return ref