# 動体検知ライブラリ libmotion.so のビルド
#   make        ... libmotion.so を作る
#   make clean  ... 生成物を消す

CC      ?= gcc
CFLAGS  ?= -O2
LDFLAGS ?=

libmotion.so: motion.c
	$(CC) $(CFLAGS) -shared -fPIC -o $@ $< $(LDFLAGS)

.PHONY: clean
clean:
	rm -f libmotion.so
