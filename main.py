from cvfile import cvfun
from control import controlfun
import threading

def main():
    lane_data={}
    lanes=int(input("Enter number of lanes:"))

    for i in range(lanes):
        data=cvfun(i)
        lane_data[i]=data

    controlfun(lane_data,lanes)

if __name__ == "__main__":
    main()

