import joblib
import pandas as pd
import numpy as np


class RealtimeDetector:

    def __init__(self, model_path):

        self.model = joblib.load(model_path)

    def predict(self, features):

        X = pd.DataFrame([features])

        prediction = self.model.predict(X)[0]

        confidence = float(
            np.max(
                self.model.predict_proba(X)
            )
        )

        return {
            "label": str(prediction),
            "confidence": round(confidence, 4)
        }