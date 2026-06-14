import numpy as np
import mediapipe as mp

from mediapipe.tasks import python
from mediapipe.tasks.python import vision


class CaptureDetector:

    IMPORTANT_LANDMARKS = [
        11, 12,
        13, 14,
        15, 16
    ]

    def __init__(self, model_path):

        self.landmarker = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=python.BaseOptions(
                    model_asset_path=model_path
                ),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=1
            )
        )

    @staticmethod
    def arm_direction_angle(
        shoulder_x,
        shoulder_y,
        wrist_x,
        wrist_y
    ):
        return np.degrees(
            np.arctan2(
                wrist_y - shoulder_y,
                wrist_x - shoulder_x
            )
        )

    def extract_features(self, image_rgb):

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=image_rgb
        )

        result = self.landmarker.detect(mp_image)

        if not result.pose_landmarks:
            return None

        landmarks = result.pose_landmarks[0]

        features = []

        for idx in self.IMPORTANT_LANDMARKS:

            lm = landmarks[idx]

            features.extend([
                lm.x,
                lm.y,
                lm.z
            ])

        left_dir = self.arm_direction_angle(
            landmarks[11].x,
            landmarks[11].y,
            landmarks[15].x,
            landmarks[15].y
        )

        right_dir = self.arm_direction_angle(
            landmarks[12].x,
            landmarks[12].y,
            landmarks[16].x,
            landmarks[16].y
        )

        features.append(left_dir)
        features.append(right_dir)

        return features