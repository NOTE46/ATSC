from control import controlfun

def minput(lanes):
    
    data={}
    print(f"Number of lanes:{lanes}")

    try:

        for i in range(lanes):
            data[i]={"density":0,"ambulance":False}

            while True:
                data[i]["density"]=int(input(f"Enter no of vehicles in lane {i+1}:"))
                if data[i]["density"] < 0:
                    print("Incorrect input (Enter positive value)")
                    continue
                break
            while True:
                amb=int(input(f"Enter no of ambulance (0 if none):"))
                if amb < 0:
                    print("Invalid (Enter positive value)")
                    continue
                elif amb==0:
                    data[i]["ambulance"]=False
                else:
                    data[i]["ambulance"]=True
                break
            
    except Exception as e:
        print(f"{e}, Program Terminated")
        return

    result=controlfun(data,lanes)

    print(f"Lane no:{result['lane_no']+1}\nSignal:{result['signal']}")



        

            