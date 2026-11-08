from control import controlfun


def minput(lanes):
    """
    Prompt for vehicle count and emergency vehicle per lane,
    invoke controlfun, and display the selected green lane.
    """
    data = {}
    print(f"Number of lanes:{lanes}")

    try:
        for i in range(lanes):
            while True:
                try:
                    val = int(input(f"Enter no of vehicles in lane {i + 1}:"))
                    if val < 0:
                        print("Incorrect input (Enter positive value)")
                        continue
                    density = val
                    break
                except ValueError:
                    print("Invalid input (Enter an integer)")

            while True:
                try:
                    ev = int(input(
                        f"Enter emergency vehicle in lane {i + 1} "
                        "(0 = None, 1 = Ambulance, 2 = Firetruck, > 2 = Ambulance):"
                    ))
                    if ev < 0:
                        print("Invalid (Enter positive value)")
                        continue
                    if ev == 0:
                        ambulance = False
                        emergency = False
                        emergency_type = "none"
                    elif ev == 2:
                        ambulance = False
                        emergency = True
                        emergency_type = "firetruck"
                    else:  # 1 or > 2
                        ambulance = True
                        emergency = True
                        emergency_type = "ambulance"
                    break
                except ValueError:
                    print("Invalid input (Enter an integer)")

            data[i] = {
                "density": density,
                "ambulance": ambulance,
                "emergency": emergency,
                "emergency_type": emergency_type,
            }

    except (Exception, KeyboardInterrupt) as e:
        print(f"{e}, Program Terminated")
        return None

    result = controlfun(data, lanes)
    print(f"Lane no:{result['lane_no'] + 1}\nSignal:{result['signal']}")
    return result