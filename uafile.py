from ultralytics import YOLO
from collections import defaultdict

vehiclecount=defaultdict(int)

model = YOLO("best.pt")

def uamodel(frame):
        global vehiclecount, model

        results=model(frame)

        for box in results[0].boxes:
            label=results[0].names[int(box.cls)]

            if label=="car":
                vehiclecount["car"]+=1
            if label =="motorcycle":
                vehiclecount["motorcycle"]+=1
            if label =="person":
                vehiclecount["person"]+=1

        print(f"No of cars:{vehiclecount['car']}\nNo of motorcycle:{vehiclecount['motorcycle']}\nNo of person:{vehiclecount['person']}")
    