from ultralytics import YOLO

model_v=r'Model\best.pt'
model=YOLO(model_v)
def ambulance_detect(frame):

    results=model(frame)

    for box in results[0].boxes:
        label=results[0].names[int(box.cls)]

        if label == 'ambulance':
            return True
    
    return False
        
    