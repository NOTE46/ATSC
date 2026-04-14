from cvfile import cvfun
import threading

lanes=int(input("Enter number of lanes:"))

for i in range(lanes):
    cvfun(i)