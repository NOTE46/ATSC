from cvfile import cvfun
from control import controlfun
import threading

if __name__ == "__main__":
    lane_data={}
    lanes=int(input("Enter number of lanes:"))

    for i in range(lanes):
        data=cvfun(i)
        lane_data[i]=data

    controlfun(lane_data,lanes)

