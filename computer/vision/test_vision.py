import threading
from image_receiver_class import ImageReceiver
from computer_vision_class import ComputerVision

# 1. Instancia as peças separadamente
meu_receiver = ImageReceiver()
minha_visao = ComputerVision(receiver=meu_receiver)

# 2. Conecta a visão no receiver
meu_receiver.SetImageProcesser(minha_visao)

# 3. CRIAÇÃO DA THREAD DA CÂMERA
thread_camera = threading.Thread(target=meu_receiver.Run)
thread_camera.start()

# 4. INICIA O PROCESSAMENTO NA THREAD PRINCIPAL
# IMPORTANTE: O OpenCV (cv2.imshow) exige rodar na via principal do sistema operacional.
minha_visao.Run()

# 5. DESLIGAMENTO SEGURO
# Quando a Vision() fechar (apertando 'q'), ela manda o Receiver dar 'Finish()'.
# O comando join() garante que o programa só termine de fechar totalmente 
# quando a thread da câmera encerrar suas atividades em segurança.
thread_camera.join()
print("Sistema encerrado com segurança.")