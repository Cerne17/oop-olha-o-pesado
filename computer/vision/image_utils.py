import cv2
import mediapipe as mp

def write_gesture_name(img,gesto,bbox):
    """
    Escreve uma mensagem na tela que identifica o gesto que está sendo feito.
    Essa mensagem é escrita logo acima da bounding box da pessoa.
    """

    x1, y1, x2, y2 = bbox

    # Coordenadas do texto (x1 da caixa, e um pouco acima do y1)
    text_pos = (x1, max(30, y1 - 10))

    if gesto == "ROCK":
        cv2.putText(img, r"ROCK ON! \m/", text_pos, cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
    elif gesto == "STOP":
        cv2.putText(img, r"STOP! \m/", text_pos, cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    elif gesto == "JOIA":
        cv2.putText(img, r"JOIA! \m/", text_pos, cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    else:
        pass
    return img

def draw_squeleton(img, hand_lms):
    """
    Desenha o esqueleto da mão na imagem para mostrar o que está sendo lido pelo mediapipe
    """
    h, w, _ = img.shape
    for lm in hand_lms:
        cx, cy = int(lm.x * w), int(lm.y * h)
        cv2.circle(img, (cx, cy), 5, (255, 0, 0), -1)

    connections = mp.tasks.vision.HandLandmarksConnections.HAND_CONNECTIONS
    for conn in connections:
        start = hand_lms[conn.start]
        end = hand_lms[conn.end]
        cv2.line(img,
                    (int(start.x * w), int(start.y * h)),
                    (int(end.x * w), int(end.y * h)),
                    (0, 255, 0), 2)
    return img

def draw_person_box(img, box, has_gesture=False):
    """
    Desenha a bounding box ao redor da pessoa.
    Se a pessoa estiver fazendo um gesto (has_gesture=True), a caixa fica verde.
    Caso contrário, a caixa fica vermelha (ou a cor original que preferir).
    """
    x1, y1, x2, y2 = box
    
    if has_gesture:
        color = (0, 255, 0)  # Verde (Alvo Ativo)
        thickness = 3
    else:
        color = (0, 0, 255)  # Vermelho (Apenas Detectado)
        thickness = 2
        
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    return img