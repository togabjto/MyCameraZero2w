#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// 前回のフレームを記憶しておくためのポインタ
static unsigned char* prev_frame = NULL;

// Pythonから呼ばれる動体検知関数
// current_frame: Pythonから渡される白黒画像の配列
// width, height: 画像の幅と高さ
int detect_motion(unsigned char* current_frame, int width, int height) {
    int size = width * height;
    int threshold = 30; // ピクセルの色の変化を検知する閾値（感度）
    int changed_pixels = 0;
    
    // 画面全体の何％が変化したら「動いた」と判定するか（ここでは3%）
    int motion_trigger_count = (int)(size * 0.03); 

    // 初回実行時は比較対象がないので、現在のフレームを記憶して終了
    if (prev_frame == NULL) {
        prev_frame = (unsigned char*)malloc(size);
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