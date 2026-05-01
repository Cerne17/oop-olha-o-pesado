import cv2

class ImageReceiver():
    def __init__(self):
        self.actual_image = None
        self.actual_image_rgb = None
        self.image_processer = None
        self.cap = cv2.VideoCapture(0)
        self.finish = False
    
    def SetImageProcesser(self,image_processer):
        self.image_processer = image_processer
    
    def Run(self):
        while self.cap.isOpened() and not self.finish:
            success = self.ReceiveImage()
            if success:
                self.NotifyNewImageReady()
        self.CloseImages()
    
    def GetImage(self):
        return self.actual_image, self.actual_image_rgb
    
    def NotifyNewImageReady(self):
        self.image_processer.NotifyNewImage()
    
    def ReceiveImage(self):
        success, img = self.cap.read()
        img = cv2.resize(img, (640, 480)) # Usada para diminuir gasto computacional

        if not success:
            return False
        
        img = cv2.flip(img, 1)  # Inverter para efeito de espelho
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.actual_image = img
        self.actual_image_rgb = img_rgb
        return True
    
    def CloseImages(self):
        if self.cap is not None:
            self.cap.release()
        cv2.destroyAllWindows()
    
    def Finish(self):
        self.finish = True