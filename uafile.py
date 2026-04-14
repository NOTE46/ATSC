from ultralytics import YOLO
from collections import defaultdict
import cv2 as cv
from ambdet import ambulance_detect
#vehiclecount to count number of indivitual vehicles and density for how many vehicles
vehiclecount=defaultdict(int)

model_path=r'Model\yolov8n.pt'
model = YOLO(model_path)

#read the video from camera and give feedback of what types of object present
def uamodel(frame):
        
        global vehiclecount, model

        #process per frame and init density to count number of objects
        results=model(frame)
        density = 0

        #saving the labels
        for box in results[0].boxes:
            label=results[0].names[int(box.cls)]

            if label=="car":
                vehiclecount["car"]+=1
                density+=1
            elif label =="motorcycle":
                vehiclecount["motorcycle"]+=1
                density+=1
            elif label =="truck":
                if ambulance_detect(frame) is True:
                     vehiclecount["ambulance"]+=1
                     density+=1
                     continue
                else:     
                    vehiclecount["truck"]+=1
                    density+=1
            else:
                 continue
                  
        print(f"No of cars:{vehiclecount['car']}\nNo of motorcycle:{vehiclecount['motorcycle']}\nDensity:{density}")
    