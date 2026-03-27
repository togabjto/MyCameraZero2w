#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>

// --- Motion Detection Parameters ---
// Skipping 500 bytes (equivalent to 400 pixels in pBAA 10-bit format)
#define SKIP_BYTES 500 
#define PIXEL_THRESHOLD 20
#define MOTION_THRESHOLD 100

int main() {
    int fd = open("/dev/video0", O_RDWR);
    if (fd < 0) { perror("[ERROR] Cannot open camera"); return 1; }

    struct v4l2_format fmt = {0};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    ioctl(fd, VIDIOC_G_FMT, &fmt);
    
    printf("Starting V4L2 Motion Detection...\n");
    printf("Resolution: %dx%d\n", fmt.fmt.pix.width, fmt.fmt.pix.height);

    struct v4l2_requestbuffers req = {0};
    req.count = 1;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    ioctl(fd, VIDIOC_REQBUFS, &req);

    struct v4l2_buffer buf = {0};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    buf.index = 0;
    ioctl(fd, VIDIOC_QUERYBUF, &buf);

    void *buffer_start = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, buf.m.offset);
    
    int type = buf.type;
    ioctl(fd, VIDIOC_STREAMON, &type);

    // Variables for motion detection (Lovely Ice's logic!)
    uint8_t *prev_frame = NULL;
    size_t prev_len = 0;

    // Continuous capture loop
    while (1) {
        ioctl(fd, VIDIOC_QBUF, &buf);
        if (ioctl(fd, VIDIOC_DQBUF, &buf) < 0) {
            perror("[ERROR] Failed to dequeue");
            break;
        }

        // Initialize previous frame buffer on first run
        if (prev_frame == NULL) {
            prev_len = buf.bytesused / SKIP_BYTES;
            prev_frame = (uint8_t*)malloc(prev_len);
            for (size_t i = 0, j = 0; i < buf.bytesused && j < prev_len; i += SKIP_BYTES, j++) {
                // Grab the 1st byte of the 5-byte block (upper 8-bits of a pixel)
                prev_frame[j] = ((uint8_t*)buffer_start)[i];
            }
            printf("Initial frame saved. Monitoring started...\n");
            continue;
        }

        // Compare current frame with previous frame
        int changed_pixels = 0;
        for (size_t i = 0, j = 0; i < buf.bytesused && j < prev_len; i += SKIP_BYTES, j++) {
            uint8_t current_pixel = ((uint8_t*)buffer_start)[i];
            uint8_t prev_pixel = prev_frame[j];

            if (abs(current_pixel - prev_pixel) > PIXEL_THRESHOLD) {
                changed_pixels++;
            }
            prev_frame[j] = current_pixel; // Update for next comparison
        }

        printf("Changed pixels: %d\n", changed_pixels);

        if (changed_pixels > MOTION_THRESHOLD) {
            printf("!!! MOTION DETECTED !!!\n");
            
            // 1. Save the RAW data
            FILE *f = fopen("raw_sensor_data.bin", "wb");
            if (f) {
                fwrite(buffer_start, 1, buf.bytesused, f);
                fclose(f);
                printf("Saved raw data. Triggering Python develop script...\n");
                
                // 2. Pass the baton to Python!
                system("python3 develop.py");
                printf("Python finished. Resuming monitor...\n");
            }
        }
        
        // Wait 0.2 seconds to avoid spamming the console
        usleep(200000); 
    }

    ioctl(fd, VIDIOC_STREAMOFF, &type);
    munmap(buffer_start, buf.length);
    if (prev_frame) free(prev_frame);
    close(fd);
    return 0;
}