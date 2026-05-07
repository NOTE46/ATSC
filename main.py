from cvfile import Cameraf
from control import controlfun
import time
import threading

TIME_INTERVAL=2
def main():
    
    lanes=int(input("Enter number of lanes:"))

    camera={}
    for i in range(lanes):
        camera[i]=Cameraf(i,i)

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

