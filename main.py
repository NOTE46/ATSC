import json
import os
from pathlib import Path
import threading
import time

try:
    from control import controlfun, reset_control
except ImportError:
    from control import controlfun
    def reset_control():
        pass

try:
    from cvfile import Cameraf, scan_all_lanes
except ImportError:
    from cvfile import Cameraf
    def scan_all_lanes(cameras, live=False):
        return {}, {}

from manual_io import minput

TIME_INTERVAL = 2


def load_config():
    cfg_path = Path("config.json")
    if cfg_path.exists():
        try:
            with open(cfg_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def clean_path(p):
    return p.strip().strip('"').strip("'")

def main():
    config = load_config()
    green_options = config.get("green_options", [15, 30, 40, 50, 60])
    default_green = config.get("default_green", 30)
    yellow_time = config.get("yellow_time", 5)

    try:
        n = 0
        while True:
            ty = int(input("Enter input type (0 for live camera) (1 for video) (2 for manual):"))

            if ty == 0:
                lanes = int(input("Enter number of lanes:"))
                break
            elif ty == 1:
                lanes = int(input("Enter number of videos:"))
                break
            elif ty == 2:
                lanes = int(input("Enter number of lanes:"))
                break
            else:
                print("Invalid input, Enter again!")
                n += 1

            if n >= 5:
                print("Multiple invalid input,Program Terminated")
                return

    except ValueError:
        print("Please enter a valid number! (Number)\nProgram Terminated")
        return

    # Prompt user for green cycle time after mode/lane selection
    opts_str = ", ".join(str(x) for x in green_options)
    raw_green = input(f"Select green signal duration in seconds ({opts_str}) [default {default_green}]: ").strip()
    try:
        val = int(raw_green)
        green_time = val if val in green_options else default_green
    except (ValueError, TypeError):
        green_time = default_green

    if ty == 2:
        minput(lanes)
        return

    camera = {}
    for i in range(lanes):
        if ty == 0:
            camera[i] = Cameraf(i, i)
        else:
            path = clean_path(input("Enter video path:"))
            camera[i] = Cameraf(i, path)

    try:
        reset_control()
        lane_data, frames = scan_all_lanes(camera, live=False)
        results = controlfun(lane_data, lanes)
        active_lane = results["lane_no"]
        print(f"\n[BOOT SCAN COMPLETE] Initial Active Lane: {active_lane + 1} (GREEN for {green_time}s)")

        while True:
            next_decision = [None]
            scan_data = [None]
            scan_thread = None

            for remaining in range(green_time, 0, -1):
                if remaining > yellow_time:
                    print(f"[Lane {active_lane + 1} GREEN] Time remaining: {remaining}s")
                    time.sleep(1)
                elif remaining == yellow_time:
                    print(f"[Lane {active_lane + 1} YELLOW] Switching in {remaining}s — scanning traffic...")

                    def _cli_scan():
                        try:
                            data, _ = scan_all_lanes(camera, live=False)
                            scan_data[0] = data
                            next_decision[0] = controlfun(data, lanes)
                        except Exception as e:
                            print(f"Scan error: {e}")
                            next_decision[0] = {"lane_no": (active_lane + 1) % lanes, "signal": "Green"}

                    scan_thread = threading.Thread(target=_cli_scan, daemon=True)
                    scan_thread.start()
                    time.sleep(1)
                else:
                    print(f"[Lane {active_lane + 1} YELLOW] Switching in {remaining}s")
                    time.sleep(1)

            # At countdown expiry (0): join scan thread (timeout=2)
            if scan_thread is not None:
                scan_thread.join(timeout=2)

            prev_lane = active_lane
            if next_decision[0] is not None and "lane_no" in next_decision[0]:
                active_lane = next_decision[0]["lane_no"]
            else:
                active_lane = (prev_lane + 1) % lanes

            # Print cycle summary
            active_density = scan_data[0][active_lane].get("density", 0) if (scan_data[0] and active_lane in scan_data[0]) else "N/A"
            active_emerg = scan_data[0][active_lane].get("emergency_type", "none") if (scan_data[0] and active_lane in scan_data[0]) else "none"
            print(f"\n{'='*55}")
            print(f"CYCLE SUMMARY: Lane {prev_lane + 1} -> Lane {active_lane + 1} GREEN")
            print(f"Winner Density: {active_density} | Emergency: {str(active_emerg).upper()}")
            print(f"{'='*55}\n")

    except KeyboardInterrupt:
        print("Stopped")
    except Exception as e:
        print(f"Error : {e}")

    finally:
        for c in camera.values():
            try:
                c.releasevid()
            except Exception:
                pass


if __name__ == "__main__":
    main()

