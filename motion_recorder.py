while True:
        # ストリームからJPGを切り出す（ここはそのまま）
        buffer += proc.stdout.read(4096)
        a = buffer.find(b'\xff\xd8')
        b = buffer.find(b'\xff\xd9')
        
        if a != -1 and b != -1:
            jpg_data = buffer[a:b+2]
            buffer = buffer[b+2:]
            
            frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None: continue

            # --- [1. 負荷削減：解析用に超軽量化] ---
            # 1280x720の重い処理を避けるため、160x90にリサイズして計算
            search_frame = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)
            gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

            if avg is None:
                # リサイズしたサイズに合わせて背景を初期化
                avg = gray_blur.copy().astype("float")
                continue

            # --- [2. 動体検知ロジック（軽量画像で実行）] ---
            cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
            frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            max_area = 0
            if contours:
                # 面積の閾値もリサイズに合わせて調整が必要（160x90なら500〜1000くらいが目安）
                max_area = max([cv2.contourArea(c) for c in contours])

            # --- [3. 録画制御（保存は高画質な frame を使用）] ---
            current_time = time.time()
            timestamp_str = datetime.now().strftime("%H:%M:%S")

            if max_area > THRESHOLD_AREA:
                record_until = current_time + EXTEND_SECONDS
                if not is_recording:
                    filename = os.path.join(SAVE_DIR, datetime.now().strftime("%Y%m%d_%H%M%S.mp4"))
                    h, w = frame.shape[:2] # 高画質側のサイズ(1280x720)を取得
                    # フレームレートを cmd の設定(10.0)に合わせる
                    out = cv2.VideoWriter(filename, fourcc, 10.0, (w, h)) 
                    is_recording = True
                    print(f"\n[{timestamp_str}] >>> RECORDING STARTED: {filename}")

            if is_recording:
                out.write(frame) # ここは高画質な「元のframe」を書き込む
                
                if current_time > record_until:
                    out.release()
                    is_recording = False
                    # avg = None  <-- ここ消すと背景が安定します（お好みで）
                    print(f"\n[{timestamp_str}] <<< RECORDING STOPPED & SAVED")

            status = "REC" if is_recording else "---"
            print(f"\r[{timestamp_str}] Status: {status} | Area: {max_area:6.0f} ", end="", flush=True)