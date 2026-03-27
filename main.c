#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>

// 保存する解像度（Zero 2 Wに優しい低解像度から試そう）
#define WIDTH  640
#define HEIGHT 480

int main() {
    int fd = open("/dev/video0", O_RDWR);
    if (fd < 0) { perror("[ERROR] カメラが開けません"); return 1; }

    // 【魔法のポイント】C言語側からは「標準的なYUYV」を要求する
    // これがV3カメラ直接だと Invalid argument になる原因。
    struct v4l2_format fmt = {0};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = WIDTH;
    fmt.fmt.pix.height = HEIGHT;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUYV; // 色付き画像を要求
    fmt.fmt.pix.field = V4L2_FIELD_NONE;

    if (ioctl(fd, VIDIOC_S_FMT, &fmt) < 0) {
        perror("[ERROR] フォーマット設定失敗。V3カメラは直接 YUYV を扱えません");
        close(fd); return 1;
    }

    // メモリの確保（バッファ1枚）
    struct v4l2_requestbuffers req = {0};
    req.count = 1;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    ioctl(fd, VIDIOC_REQBUFS, &req);

    // メモリのマッピング
    struct v4l2_buffer buf = {0};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    buf.index = 0;
    ioctl(fd, VIDIOC_QUERYBUF, &buf);

    void *buffer_start = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, buf.m.offset);

    // 撮影開始
    ioctl(fd, VIDIOC_QBUF, &buf);
    int type = buf.type;
    ioctl(fd, VIDIOC_STREAMON, &type);

    printf("カシャッ！（写真を撮影中...）\n");
    sleep(2); // V3 Noirが明るさを調整する時間を稼ぐ

    // データの取得
    ioctl(fd, VIDIOC_DQBUF, &buf);

    // 【重要】YUYVの生データ（RAW画像ではない）をファイルに保存
    // JPEGにするにはさらに変換が必要だけど、まずは画像データを引っこ抜く！
    FILE *f = fopen("output.yuv", "wb");
    if (f) {
        fwrite(buffer_start, 1, buf.bytesused, f);
        fclose(f);
        printf("[SUCCESS] 'output.yuv' に保存しました！ (%dx%d YUYV形式)\n", WIDTH, HEIGHT);
    }

    // 後片付け
    ioctl(fd, VIDIOC_STREAMOFF, &type);
    munmap(buffer_start, buf.length);
    close(fd);
    return 0;
}