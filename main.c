#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>

int main() {
    int fd = open("/dev/video0", O_RDWR);
    if (fd < 0) { perror("[ERROR] Cannot open camera"); return 1; }

    struct v4l2_format fmt = {0};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(fd, VIDIOC_G_FMT, &fmt) < 0) {
        perror("[ERROR] Failed to get format");
        close(fd); return 1;
    }

    printf("--- Current Camera Settings ---\n");
    printf("Format: %c%c%c%c\n", 
           fmt.fmt.pix.pixelformat & 0xFF, (fmt.fmt.pix.pixelformat >> 8) & 0xFF,
           (fmt.fmt.pix.pixelformat >> 16) & 0xFF, (fmt.fmt.pix.pixelformat >> 24) & 0xFF);
    printf("Resolution: %dx%d\n", fmt.fmt.pix.width, fmt.fmt.pix.height);
    printf("-------------------------------\n");

    struct v4l2_requestbuffers req = {0};
    req.count = 1;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (ioctl(fd, VIDIOC_REQBUFS, &req) < 0) {
        perror("[ERROR] Failed to request buffers");
        return 1;
    }

    struct v4l2_buffer buf = {0};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    buf.index = 0;
    if (ioctl(fd, VIDIOC_QUERYBUF, &buf) < 0) {
        perror("[ERROR] Failed to query buffer");
        return 1;
    }

    void *buffer_start = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, buf.m.offset);
    if (buffer_start == MAP_FAILED) {
        perror("[ERROR] Memory mapping failed");
        return 1;
    }

    if (ioctl(fd, VIDIOC_QBUF, &buf) < 0) {
        perror("[ERROR] Failed to queue buffer");
        return 1;
    }
    int type = buf.type;
    if (ioctl(fd, VIDIOC_STREAMON, &type) < 0) {
        perror("[ERROR] STREAMON failed");
        return 1;
    }

    printf("Capturing RAW data...\n");

    if (ioctl(fd, VIDIOC_DQBUF, &buf) < 0) {
        perror("[ERROR] Failed to dequeue buffer");
        return 1;
    }

    FILE *f = fopen("raw_sensor_data.bin", "wb");
    if (f) {
        fwrite(buffer_start, 1, buf.bytesused, f);
        fclose(f);
        printf("[SUCCESS] Saved %d bytes to 'raw_sensor_data.bin'\n", buf.bytesused);
    }

    ioctl(fd, VIDIOC_STREAMOFF, &type);
    munmap(buffer_start, buf.length);
    close(fd);

    return 0;
}