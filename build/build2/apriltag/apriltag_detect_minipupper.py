import subprocess
import numpy as np
import cv2
import apriltag
import os

W, H = 640, 480
RAW_FILE = "frame.raw"

def capture_raw_frame():
    cmd = [
        "v4l2-ctl", "-d", "/dev/video0",
        "--set-fmt-video=width=640,height=480,pixelformat=GB10",
        "--stream-mmap",
        "--stream-skip=20",
        "--stream-count=1",
        f"--stream-to={RAW_FILE}"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"v4l2-ctl failed:\\n{result.stderr}")

    if not os.path.exists(RAW_FILE):
        raise RuntimeError("frame.raw was not created")

def raw_to_bgr():
    raw = np.fromfile(RAW_FILE, dtype=np.uint16).reshape((H, W))

    raw = raw[1:-1, 1:-1]

    lo = np.percentile(raw, 1)
    hi = np.percentile(raw, 99.5)

    scaled = np.clip((raw - lo) * 255.0 / max(hi - lo, 1), 0, 255).astype(np.uint8)
    img = cv2.cvtColor(scaled, cv2.COLOR_BAYER_GB2BGR)
    return img

def main():
    options = apriltag.DetectorOptions(families="tag36h11")
    detector = apriltag.Detector(options)

    while True:
        capture_raw_frame()
        frame = raw_to_bgr()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        results = detector.detect(gray)

        if results:
            for r in results:
                print(f"Detected tag ID: {r.tag_id}")

                corners = r.corners.astype(int)
                for i in range(4):
                    p0 = tuple(corners[i])
                    p1 = tuple(corners[(i + 1) % 4])
                    cv2.line(frame, p0, p1, (0, 255, 0), 2)

                center = tuple(r.center.astype(int))
                cv2.circle(frame, center, 5, (0, 0, 255), -1)
                cv2.putText(
                    frame,
                    f"ID: {r.tag_id}",
                    (center[0] + 10, center[1]),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2
                )
        else:
            print("No tag detected")

        cv2.imshow("AprilTag Detection", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
