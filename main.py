#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>

int main() {
    // 1. カメラの窓口を開く
    int fd = open("/dev/video0", O_RDWR);
    if (fd < 0) {
        perror("[ERROR] カメラが開けません");
        return 1;
    }

    // 2. 【ここがキモ！】カメラに「今どんな生データ出せる？」と聞く
    // 無理やり形式を押し付ける(S_FMT)とエラーになるので、今の状態を取得(G_FMT)する
    struct v4l2_format fmt = {0};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(fd, VIDIOC_G_FMT, &fmt) < 0) {
        perror("[ERROR] フォーマットの取得に失敗しました");
        close(fd);
        return 1;
    }

    printf("--- カメラの現在の設定 ---\n");
    printf("フォーマット: %c%c%c%c\n", 
           fmt.fmt.pix.pixelformat & 0xFF, (fmt.fmt.pix.pixelformat >> 8) & 0xFF,
           (fmt.fmt.pix.pixelformat >> 16) & 0xFF, (fmt.fmt.pix.pixelformat >> 24) & 0xFF);
    printf("解像度: %dx%d\n", fmt.fmt.pix.width, fmt.fmt.pix.height);
    printf("--------------------------\n");

    // 3. ラズパイのメモリ（バッファ）を1枚分だけ要求する
    struct v4l2_requestbuffers req = {0};
    req.count = 1;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (ioctl(fd, VIDIOC_REQBUFS, &req) < 0) {
        perror("[ERROR] メモリの確保に失敗しました");
        return 1;
    }

    // 4. メモリをプログラムとカメラで繋ぐ（マッピング）
    struct v4l2_buffer buf = {0};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    buf.index = 0;
    if (ioctl(fd, VIDIOC_QUERYBUF, &buf) < 0) {
        perror("[ERROR] バッファのクエリに失敗しました");
        return 1;
    }

    void *buffer_start = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, buf.m.offset);
    if (buffer_start == MAP_FAILED) {
        perror("[ERROR] メモリマッピングに失敗しました");
        return 1;
    }

    // 5. 録画キューに入れて、ストリーム開始！
    if (ioctl(fd, VIDIOC_QBUF, &buf) < 0) {
        perror("[ERROR] キューの追加に失敗しました");
        return 1;
    }
    int type = buf.type;
    if (ioctl(fd, VIDIOC_STREAMON, &type) < 0) {
        perror("[ERROR] 撮影の開始(STREAMON)に失敗しました");
        return 1;
    }

    printf("カシャッ！(RAWデータを取得中...)\n");

    // 6. 撮影した生データを引っこ抜く！
    if (ioctl(fd, VIDIOC_DQBUF, &buf) < 0) {
        perror("[ERROR] データの取得に失敗しました");
        return 1;
    }

    // 7. 生データをそのままバイナリファイルとして保存
    FILE *f = fopen("raw_sensor_data.bin", "wb");
    if (f) {
        fwrite(buffer_start, 1, buf.bytesused, f);
        fclose(f);
        printf("[SUCCESS] %d バイトの生データを 'raw_sensor_data.bin' に保存しました！\n", buf.bytesused);
    }

    // 8. お片付け
    ioctl(fd, VIDIOC_STREAMOFF, &type);
    munmap(buffer_start, buf.length);
    close(fd);

    return 0;
}