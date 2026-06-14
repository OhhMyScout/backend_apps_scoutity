import cv2
import numpy as np

from .capture import CaptureDetector
from .realtime import RealtimeDetector


class DetectionPackage:

    def __init__(self):

        self.capture = CaptureDetector(
            "data\\models\\pose_landmarker_full.task"
        )

        self.detector = RealtimeDetector(
            "data\\models\\semaphore_rf.pkl"
        )

    def process_frame(self, image_bytes):

        image_array = np.frombuffer(
            image_bytes,
            np.uint8
        )

        image = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        image_rgb = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2RGB
        )

        features = self.capture.extract_features(
            image_rgb
        )

        if features is None:

            return {
                "success": False,
                "message": "Pose tidak terdeteksi"
            }

        prediction = self.detector.predict(
            features
        )

        return {
            "success": True,
            "result": prediction
        }