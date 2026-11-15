#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// 前回のフレームを記憶しておくためのポインタ
static unsigned char* prev_frame = NULL;
// prev_frame を確保したときのサイズ（画像サイズが途中で変わった場合の検出用）
static int prev_size = 0;

// Pythonから呼ばれる動体検知関数
// current_frame: Pythonから渡される白黒画像の配列
// width, height: 画像の幅と高さ
// 戻り値: 1 = 動きあり, 0 = 動きなし（初回・サイズ変更直後を含む）, -1 = 引数不正またはメモリ確保に失敗
int detect_motion(unsigned char* current_frame, int width, int height) {
    // 引数の確認
    if (current_frame == NULL || width <= 0 || height <= 0) {
        return -1;
    }
    int size = width * height;
    int threshold = 30; // ピクセルの色の変化を検知する閾値（感度）
    int changed_pixels = 0;
    
    // 画面全体の何％が変化したら「動いた」と判定するか（ここでは3%）
    int motion_trigger_count = (int)(size * 0.03); 

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

    // すべてのピクセルをチェックして、前回との差を計算
    for (int i = 0; i < size; i++) {
        int diff = abs(current_frame[i] - prev_frame[i]);
        if (diff > threshold) {
            changed_pixels++;
        }
    }

    // 現在のフレームを次回の比較用に上書き保存
    memcpy(prev_frame, current_frame, size);

    // 変化したピクセル数が基準を超えていたら「1（検知）」を返す
    if (changed_pixels > motion_trigger_count) {
        return 1; 
    }
    
    return 0; // 検知なし
}