from cvfile import Cameraf
from control import controlfun
import time
from manual_io import minput

TIME_INTERVAL=2
def main():

    try:
        n=0
        while(True):

            ty=int(input("Enter input type (0 for live camera) (1 for video) (2 for manual):"))
    
            if(ty == 0):
                lanes=int(input("Enter number of lanes:"))
                break
            elif(ty == 1):
                lanes=int(input("Enter number of videos:"))
                break
            elif(ty == 2):
                lanes=int(input("Enter number of lanes:"))
                break
            else:
                print("Invalid input, Enter again!")
                n+=1

            if n >=5:
                print("Multiple invalid input,Program Terminated")
                return

    except ValueError as e:
        print(f"Please enter a valid number! (Number)\nProgram Terminated")
        return
        
    camera={}

    if ty== 2:
        minput(lanes)
        return

    for i in range(lanes):
        if(ty == 0):
            camera[i]=Cameraf(i,i)
        else:
            path=input("Enter video path:")
            camera[i]=Cameraf(i,path)
    try:
        while True:
            lane_data={}

            for i in range(lanes):
                data=camera[i].cvfun()
                lane_data[i]=data

            results=controlfun(lane_data,lanes)
            print(f"Lane:{results['lane_no']} Signal:{results['signal']}")

            time.sleep(TIME_INTERVAL)

    except KeyboardInterrupt:
        print("Stopped")
    except Exception as e:
        print(f"Error : {e}")

    finally:
        for c in camera.values():
            c.releasevid()

if __name__ == "__main__":
    main()

