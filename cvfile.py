import cv2 as cv
import time
from uafile import uamodel

def cvfun(lane_no):

    vid=cv.VideoCapture(lane_no)

    while True:

        for i in range(5):
            vid.grab()

        rev,frame=vid.retrieve()
        
        if rev is False:
            print(f"Video capture failed on lane {lane_no}")
            break
        uamodel(frame) 
        time.sleep(2)
        
    vid.release()
    cv.destroyAllWindows()


