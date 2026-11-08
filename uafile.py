from ultralytics import YOLO
from collections import defaultdict
from ambdet import ambulance_detect
from pathlib import Path
#vehiclecount to count number of indivitual vehicles and density for how many vehicles

model_path=Path("Model")/"yolov8n.pt"
model = YOLO(model_path)

#read the video from camera and give feedback of what types of object present
def uamodel(frame):
        
        truckd=False
        vehiclecount=defaultdict(int)

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
                truckd=True
                vehiclecount["truck"]+=1
                density+=1
            
            else:
                 continue

        if truckd is True:
             if ambulance_detect(frame) is True:
                     vehiclecount["ambulance"]+=1
                     vehiclecount["truck"]-=1
    
                            
        return {
            "density": density,
            "ambulance": vehiclecount["ambulance"] > 0
        }
    