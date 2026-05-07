import cv2 as cv
from uafile import uamodel

FRAME_S=5

class Cameraf:
    def __init__(self,lane_no,source):
        self.lane_no=lane_no
        self.vid=cv.VideoCapture(source)

        if not self.vid.isOpened():
            raise RuntimeError(f"Camera failed on {lane_no}")
        
    def cvfun(self):

        for i in range(FRAME_S  ):
            self.vid.grab()

        rev,frame=self.vid.retrieve()
        
        if rev is False:
            print(f"Video capture failed on lane {self.lane_no}")
            return {"density": 0, "ambulance": False}

        data=uamodel(frame) 
        return data
    
    def releasevid(self):
        self.vid.release()


        
    


