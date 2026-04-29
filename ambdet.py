from ultralytics import YOLO
from pathlib import Path

model_v=Path("Model")/"best.pt"
model=YOLO(model_v)

def ambulance_detect(frame):

    results=model(frame)

    for box in results[0].boxes:
        label=results[0].names[int(box.cls)]

        if label == 'ambulance':
            return True
    
    return False
        
    