#!/bin/sh
# 给 `sudo -A` 用的 askpass：从环境变量 P6_SUDO_PASSWORD 读密码，不落盘、不进命令行参数。
# 只在 scripts/p6-on-server.sh 发起的那次 SSH 会话里设置该变量。
printf '%s\n' "${P6_SUDO_PASSWORD:?未设置 P6_SUDO_PASSWORD}"
