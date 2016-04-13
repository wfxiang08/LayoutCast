#!/bin/bash
set -e

# 一般有效（当个app开发的时候不存在端口冲突)
adb forward tcp:41128 tcp:41128
mkdir -p bin/lcast/values

# 下载资源
curl --silent --output bin/lcast/values/ids.xml http://127.0.0.1:41128/ids.xml
curl --silent --output bin/lcast/values/public.xml http://127.0.0.1:41128/public.xml

# 这就是为什么使用: -S bin/lcast(表示这些资源已经被占用了)
aapt package -f --auto-add-overlay -F bin/res.zip -S bin/lcast -S res/ -M AndroidManifest.xml -I /Applications/android-sdk-mac_86/platforms/android-19/android.jar

# 上传文件
curl -T bin/res.zip http://localhost:41128/pushres
# 重启系统
curl http://localhost:41128/lcast
