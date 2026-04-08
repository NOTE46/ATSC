from ultralytics import YOLO
from collections import defaultdict
import cv2 as cv
#vehiclecount to count number of indivitual vehicles and density for how many vehicles
vehiclecount=defaultdict(int)

model_path=r'Model\yolov8n.pt'
model = YOLO(r"model_path")

#read the video from camera and give feedback of what types of object present
def uamodel(frame):
        
        global vehiclecount, model

        #process per frame and init density to count number of objects
        results=model(frame)
        density = 0

        #saving the labels given
        for box in results[0].boxes:
            label=results[0].names[int(box.cls)]

            if label=="car":
                vehiclecount["car"]+=1
                density+=1
            if label =="motorcycle":
                vehiclecount["motorcycle"]+=1
                density+=1
            if label =="person":
                vehiclecount["person"]+=1
                density+=1
            if label =="truck":
                vehiclecount["truck"]+=1
                density+=1
                    
        print(f"No of cars:{vehiclecount['car']}\nNo of motorcycle:{vehiclecount['motorcycle']}\nNo of person:{vehiclecount['person']}\nDensity:{density}")
    