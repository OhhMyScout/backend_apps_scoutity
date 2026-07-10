from fastapi import (
    APIRouter,
    UploadFile,
    File,
    HTTPException
)

from .package import DetectionPackage


detector = DetectionPackage()


def init_detection_router():

    router = APIRouter()

    @router.post("/deteksi/semaphore")
    async def detect_semaphore(
        file: UploadFile = File(...)
    ):

        try:

            image_bytes = await file.read()

            result = detector.process_frame(
                image_bytes
            )

            return result

        except Exception as e:

            raise HTTPException(
                status_code=500,
                detail=str(e)
            )

    return router