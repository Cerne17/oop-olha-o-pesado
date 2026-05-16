import threading
import time
from computer.vision.image_receiver_class import ImageReceiver
from computer.vision.computer_vision_class import ComputerVision
from computer.types.observers import ControlObserver
from computer.types.signals import ControlSignal

# --- ROBÔ DE MENTIRA (MOCK) ---
# Finge ser o RobotSender para imprimir as decisões da sua máquina de estados no console
# --- ROBÔ DE MENTIRA (MOCK) ---
# Finge ser o RobotSender para imprimir as decisões da sua máquina de estados no console
class DummyRobot(ControlObserver):
    def on_control(self, signal: ControlSignal) -> None:
        # Códigos ANSI para colorir o texto no terminal
        RESET = '\033[0m'
        AMARELO = '\033[93m'
        VERDE = '\033[92m'
        VERMELHO = '\033[91m'
        
        # Define a cor do terminal baseado no sinal do LED
        cor_terminal = RESET
        nome_estado = "DESLIGADO"
        
        if signal.leds == 0b001:
            cor_terminal = AMARELO
            nome_estado = "WAITING"
        elif signal.leds == 0b010:
            cor_terminal = VERDE
            nome_estado = "FOLLOWING"
        elif signal.leds == 0b100:
            cor_terminal = VERMELHO
            nome_estado = "LOST"
        
        # Monta a string de telemetria
        telemetria = f"[ROBÔ] {nome_estado:9} | Angulo: {signal.angle_deg:6.1f}° | Vel: {signal.speed_ref:5.2f} | Buzzer: {signal.buzzer}"
        
        # Imprime aplicando a cor no início e resetando no final para não colorir o terminal todo
        print(f"{cor_terminal}{telemetria}{RESET}")
        
# =======================================================
# EXECUÇÃO PRINCIPAL
# =======================================================

# 1. Instancia as peças separadamente
meu_receiver = ImageReceiver()
minha_visao = ComputerVision()
meu_robo_falso = DummyRobot()

# 2. Conecta os fios (Arquitetura Observer)
# A câmera avisa a visão, e a visão avisa o motor
meu_receiver.add_frame_observer(minha_visao)
minha_visao.add_control_observer(meu_robo_falso)

# 3. CRIAÇÃO DA THREAD DA CÂMERA
thread_camera = threading.Thread(target=meu_receiver.Run)
thread_camera.start()

print("Iniciando sistema... Faça o Duplo Rock para testar!")

# 4. INICIA O PROCESSAMENTO NA THREAD PRINCIPAL
try:
    # O OpenCV (cv2.imshow) exige rodar na via principal do sistema operacional.
    minha_visao.Run()
except KeyboardInterrupt:
    print("\nInterrupção pelo teclado recebida.")
finally:
    # 5. DESLIGAMENTO SEGURO
    minha_visao.finish = True
    meu_receiver.Finish()
    
    # Destrava o event caso ele esteja esperando, para a thread poder fechar
    minha_visao.image_event.set() 
    
    thread_camera.join()
    print("Sistema encerrado com segurança.")