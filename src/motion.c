#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// 前回のフレームを記憶しておくためのポインタ
static unsigned char* prev_frame = NULL;
// prev_frame を確保したときのサイズ（画像サイズが途中で変わった場合の検出用）
static int prev_size = 0;

// 検知のしきい値（set_motion_params で変更できる。既定値は従来と同じ）
static int pixel_threshold = 30;       // 画素の変化量がこれを超えたら「変化した画素」とみなす
static double change_ratio = 0.03;     // 変化した画素が画面全体のこの割合を超えたら「動き」とみなす

// 直近の detect_motion で計算した「変化した画素の割合」（0〜1）。メーター表示用。
static double last_ratio = 0.0;

// 自動調整用: 直近のフレームの「前フレームとの差」の分布（差が 0〜255 の画素が、それぞれ何個あるか）。
// 有効にしている間だけ集計する（無効のときは、従来と同じ処理で、速度も変わらない）。
static int hist_enabled = 0;
static int hist_valid = 0;
static unsigned int diff_hist[256];

void set_hist_enabled(int on) {
    hist_enabled = on ? 1 : 0;
    hist_valid = 0;
}

// 直近のフレームの分布を out（256 個）にコピーし、画素の総数を返す。まだ集計していなければ 0。
int get_diff_hist(unsigned int* out) {
    if (!hist_valid || out == NULL) {
        return 0;
    }
    memcpy(out, diff_hist, sizeof(diff_hist));
    return prev_size;
}

double get_last_ratio(void) { return last_ratio; }
// 現在のしきい値（メーターに、しきい値の線を引くため）
double get_change_ratio(void) { return change_ratio; }
int get_pixel_threshold(void) { return pixel_threshold; }

// しきい値を設定する。不正な値なら -1 を返し、設定は変更しない。
//   pixel: 0〜255 / ratio: 0 より大きく 1 以下
int set_motion_params(int pixel, double ratio) {
    if (pixel < 0 || pixel > 255 || !(ratio > 0.0 && ratio <= 1.0)) {
        return -1;
    }
    pixel_threshold = pixel;
    change_ratio = ratio;
    return 0;
}

// 前回のフレームの記憶を捨てる（計測で条件を切り替えるときなどに使う）
void reset_motion(void) {
    free(prev_frame);
    prev_frame = NULL;
    prev_size = 0;
}

// Pythonから呼ばれる動体検知関数
// current_frame: Pythonから渡される白黒画像の配列
// width, height: 画像の幅と高さ
// 戻り値: 1 = 動きあり, 0 = 動きなし（初回・サイズ変更直後を含む）, -1 = 引数不正またはメモリ確保に失敗
int detect_motion(unsigned char* current_frame, int width, int height) {
    last_ratio = 0.0; // 比較できなかった場合（初回・サイズ変更直後・エラー）は 0 にしておく

    // 引数の確認
    if (current_frame == NULL || width <= 0 || height <= 0) {
        return -1;
    }
    int size = width * height;
    int threshold = pixel_threshold; // ピクセルの色の変化を検知する閾値（感度）
    int changed_pixels = 0;
    
    // 画面全体の何％が変化したら「動いた」と判定するか（ここでは3%）
    int motion_trigger_count = (int)(size * change_ratio);

    // 初回実行時は比較対象がないので、現在のフレームを記憶して終了
    // 画像サイズが前回と違う場合は、比較できないので確保し直す（今回は比較せず記憶のみ）
    if (prev_frame != NULL && size != prev_size) {
        free(prev_frame);
        prev_frame = NULL;
    }

    if (prev_frame == NULL) {
        prev_frame = (unsigned char*)malloc(size);
        if (prev_frame == NULL) {
            return -1; // メモリ確保に失敗
        }
        prev_size = size;
        memcpy(prev_frame, current_frame, size);
        return 0;
    }

    if (hist_enabled) {
        // 自動調整中: 差の分布を集計し、しきい値を超えた画素数は、そこから数える（結果は、下の通常の処理と同じ）
        memset(diff_hist, 0, sizeof(diff_hist));
        for (int i = 0; i < size; i++) {
            diff_hist[abs(current_frame[i] - prev_frame[i])]++;
        }
        for (int d = threshold + 1; d < 256; d++) {
            changed_pixels += (int)diff_hist[d];
        }
        hist_valid = 1;
    } else {
        // すべてのピクセルをチェックして、前回との差を計算
        for (int i = 0; i < size; i++) {
            int diff = abs(current_frame[i] - prev_frame[i]);
            if (diff > threshold) {
                changed_pixels++;
            }
        }
    }

    last_ratio = (double)changed_pixels / size; // メーター表示用に、変化した画素の割合を残す

    // 現在のフレームを次回の比較用に上書き保存
    memcpy(prev_frame, current_frame, size);

    // 変化したピクセル数が基準を超えていたら「1（検知）」を返す
    if (changed_pixels > motion_trigger_count) {
        return 1; 
    }
    
    return 0; // 検知なし
}