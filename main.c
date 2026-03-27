import cv2
import numpy as np

width = 2304
height = 1296

print("Starting raw development process...")

# 1. Load the raw binary data captured by C program
with open("raw_sensor_data.bin", "rb") as f:
    raw_data = np.fromfile(f, dtype=np.uint8)

# pBAa format packs 4 pixels into 5 bytes (width * height * 1.25)
expected_size = int(width * height * 1.25)
if len(raw_data) < expected_size:
    print("Error: Data size is too small. Please run the C capture program again.")
    exit()

# Trim to exact expected size
raw_data = raw_data[:expected_size]

# 2. Extract the upper 8 bits from the 10-bit packed data
data_reshaped = raw_data.reshape((height, width // 4, 5))
bayer_8bit = data_reshaped[:, :, :4].reshape((height, width))

# 3. Demosaic (convert Bayer pattern to BGR color image)
# Using BG2BGR based on typical V3 NoIR sensor alignment
color_img = cv2.cvtColor(bayer_8bit, cv2.COLOR_BayerBG2BGR)

# 4. Save as JPEG
cv2.imwrite("lovely_photo.jpg", color_img)
print("Success! 'lovely_photo.jpg' has been created.")