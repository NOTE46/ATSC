def controlfun(data,lanes):

    maxi=0
    dlane=0
    for i in range(lanes):
        
        if(data[i]["ambulance"]):
            return {
                "lane_no":i,
                "signal":"Green" 
            }
        elif(maxi<data[i]["density"]):
            maxi = data[i]["density"]
            dlane=i
    return {
         "lane_no":dlane,
         "signal":"Green" 
        }