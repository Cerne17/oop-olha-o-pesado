import math
import mediapipe as mp
from ultralytics import YOLO

#########################################################
# Identificação de gestos com MediaPipe
#########################################################

def process_image(landmarker, img_rgb, timestamp):
    """Envia a imagem para a IA do MediaPipe processar de forma assíncrona."""
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
    landmarker.detect_async(mp_image, timestamp)

def identify_gesture(hand_lms):
    """Analisa as coordenadas da mão e retorna uma string com o nome do gesto."""
    fingers = []

    # 1. POLEGAR
    # Se polegar estiver para cima -> True (para identifica joinha)
    if hand_lms[4].y < hand_lms[3].y:
        fingers.append(True)
    else:
        fingers.append(False)

    # 2. OUTROS 4 DEDOS (Indicador, Médio, Anelar, Mindinho)
    tip_ids = [8, 12, 16, 20]
    for tip in tip_ids:
        if hand_lms[tip].y < hand_lms[tip - 2].y:
            fingers.append(True)
        else:
            fingers.append(False)

    # LÓGICAS DOS GESTOS
    # 0: Polegar, 1: Indicador, 2: Médio, 3: Anelar, 4: Mindinho
    # ROCK
    if fingers[1] and fingers[4] and not fingers[2] and not fingers[3]:
        return "ROCK"
    # STOP (Todos abertos)
    elif fingers[1] and fingers[2] and fingers[3] and fingers[4]:
        return "STOP"
    # JOIA
    elif fingers[0] and not fingers [1] and not fingers[2] and not fingers [3] and not fingers [4]:
        return "JOIA"
    
    return "NENHUM"


#########################################################
# Identificação de pessoa com YOLO
#########################################################

def init_person_detector(model_path="yolov8n-pose.pt"):
    """
    Inicializa o modelo YOLOv8n-pose. 
    Usa a versão 'nano' (yolov8n-pose.pt) por ser a mais rápida para rodar em tempo real.
    O download do arquivo .pt será feito automaticamente na primeira execução.
    """
    model = YOLO(model_path)
    return model

def detect_persons(model, img):
    """
    Retorna uma lista de dicionários. Cada dicionário contém a bounding box 
    e as coordenadas úteis para o código (ombros e pulsos) da pessoa detectada.
    Usa o rastreador ByteTrack para gerar IDs persistentes entre frames.
    """

    # persist=True faz YOLO lembrar do frame anterior
    # tracker="bytetrack.yaml" é um tracker rápido para evitar gargalos de processamento
    results = model.track(img, persist=True, classes=[0], verbose=False, tracker = "bytetrack.yaml")
    persons_data = []
    
    for r in results:
        # Se não achar nada ou não tiver os pontos (keypoints), ignora
        if r.boxes is None or r.keypoints is None:
            continue

        # Extrai caixas e keypoints como matrizes numéricas
        boxes = r.boxes.xyxy.cpu().numpy()
        keypoints = r.keypoints.xy.cpu().numpy()

        # Extrai os IDs de rastreamento (Se a YOLO conseguiu atribuir um)
        # Nos primeiros milissegundos, pode ser que o ID venha vazio.
        if r.boxes.id is not None:
            track_ids = r.boxes.id.int().cpu().numpy()
        else:
            track_ids = [-1] * len(boxes) # Usa -1 como "RG Provisório"

        for i in range(len(boxes)):
            x1, y1, x2, y2 = map(int, boxes[i])
            kp = keypoints[i]
            
            # O YOLO-Pose mapeia 17 pontos. 
            # Índices: 5=OmbroEsq, 6=OmbroDir, 9=PulsoEsq, 10=PulsoDir
            person_info = {
                "id": track_ids[i],
                "box": (x1, y1, x2, y2),
                "l_shoulder": kp[5],
                "r_shoulder": kp[6],
                "l_wrist": kp[9],
                "r_wrist": kp[10]
            }
            persons_data.append(person_info)
            
    return persons_data

def get_matching_person(hand_lms, persons_data, img):
    """
    Recebe os landmarks da mão e a lista de TODAS as pessoas detectadas pelo YOLO.
    1. Encontra a pessoa cujo pulso do YOLO está mais próximo do pulso do MediaPipe.
    2. Verifica se a mão do dono legítimo está acima do seu respectivo ombro.
    Retorna a pessoa vencedora, ou None se ninguém se encaixar ou se a mão estiver abaixada.
    """

    img_height, img_width, _ = img.shape

    # Pulso do MediaPipe em pixels
    mp_wrist_x = int(hand_lms[0].x * img_width)
    mp_wrist_y = int(hand_lms[0].y * img_height)

    closest_person = None
    min_distance = float('inf')  # Começa com uma distância infinita
    is_left_hand_closest = True # Variável para lembrar qual lado venceu

    # =======================================================
    # PASSO 1: Descobrir o DONO LEGÍTIMO (Apenas Menor Distância)
    # =======================================================

    for person in persons_data:
        # Posições dos punhos importantes medidos pela yolo
        yolo_l_wrist = person["l_wrist"]
        yolo_r_wrist = person["r_wrist"]

        # 1.1 Calcula as distâncias do pulso do MediaPipe para os dois pulsos do YOLO
        #(Se a coordenada for > 0, significa que o YOLO conseguiu ver o pulso)
        dist_l = math.hypot(mp_wrist_x - yolo_l_wrist[0], mp_wrist_y - yolo_l_wrist[1]) if yolo_l_wrist[0] > 0 else float('inf')
        dist_r = math.hypot(mp_wrist_x - yolo_r_wrist[0], mp_wrist_y - yolo_r_wrist[1]) if yolo_r_wrist[0] > 0 else float('inf')

        # Se a YOLO não conseguiu ver nenhum dos dois pulsos dessa pessoa, ignoramos ela
        if dist_l == float('inf') and dist_r == float('inf'):
            continue

        # 1.2 Descobre de qual lado é a mão e aplica o filtro do ombro correto
        if dist_l < dist_r:
            # A mão está mais perto do pulso ESQUERDO do YOLO.
            if dist_l < min_distance:
                min_distance = dist_l
                closest_person = person
                is_left_hand_closest = True
        else:
            # A mão está mais perto do pulso DIREITO do YOLO.
            if dist_r < min_distance:
                min_distance = dist_r
                closest_person = person
                is_left_hand_closest = False

    # =======================================================
    # PASSO 2: Validar a altura do ombro APENAS do dono legítimo
    # =======================================================
    if closest_person is not None:
        if is_left_hand_closest:
            # Testa contra o ombro esquerdo do dono
            if mp_wrist_y > closest_person["l_shoulder"][1]:
                return None # Mão do dono está abaixo do ombro, gesto ignorado!
        else:
            # Testa contra o ombro direito do dono
            if mp_wrist_y > closest_person["r_shoulder"][1]:
                return None # Mão do dono está abaixo do ombro, gesto ignorado!
            
    return closest_person