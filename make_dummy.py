import numpy as np
import cv2

img = np.zeros((100, 100, 3), dtype=np.uint8)
cv2.imwrite("dummy_face.jpg", img)
