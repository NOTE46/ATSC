import cv2 as cv
from uafile import uamodel

vid=cv.VideoCapture(0)

while True:
    rev,frame=vid.read()

    if rev is False:
         break
    uamodel(frame)   
    cv.imshow("photo",frame)
    cv.waitKey(0)

vid.release()
cv.destroyAllWindows()


