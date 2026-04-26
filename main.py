from cvfile import cvfun
from control import controlfun
import time
import threading

def main():

    lanes=int(input("Enter number of lanes:"))

    while True:
        lane_data={}

        for i in range(lanes):
            data=cvfun(i)
            lane_data[i]=data

        results=controlfun(lane_data,lanes)
        print(f"Lane:{results['lane_no']} Signal:{results['signal']}")

        time.sleep(2)

if __name__ == "__main__":
    main()

