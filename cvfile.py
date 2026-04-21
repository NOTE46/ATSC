import cv2 as cv
import time
from uafile import uamodel
from control import controlfun

def cvfun(lane_no):

    vid=cv.VideoCapture(lane_no)

    while True:

        for i in range(5):
            vid.grab()

        rev,frame=vid.retrieve()
        
        if rev is False:
            print(f"Video capture failed on lane {lane_no}")
            vid.release()
            return {"density": 0, "ambulance": False}

        data=uamodel(frame) 
        
        vid.release()
        cv.destroyAllWindows()
        time.sleep(2)
        
        return data
        
        
    


