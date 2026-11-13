#!/bin/bash
# 日常使用生产构建；仅在源码/公开配置改变时构建。旧构建保留，可显式回退。
set -e
project="$(cd "$(dirname "$0")/.." && pwd)"
frontend="$project/frontend"
logs="$project/backend/logs"
manifest="$logs/frontend-release.json"
mkdir -p "$logs"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"
mode="${QUANT_FRONTEND_MODE:-production}"
action="${1:-start}"
cd "$frontend"

healthy(){ curl -fsS --max-time 3 http://127.0.0.1:3000/invest >/dev/null 2>&1; }
port_pid(){ lsof -tiTCP:3000 -sTCP:LISTEN 2>/dev/null || true; }
field(){ node -e 'try{const v=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));console.log(v[process.argv[2]]||"")}catch{}' "$manifest" "$1"; }
fingerprint="$(node scripts/source-fingerprint.mjs)"
previous="$(field dist)"
if [ "$action" = "--rollback" ]; then
    dist="$(field previous)"
    [ -n "$dist" ] && [ -f "$frontend/$dist/BUILD_ID" ] || { echo "没有可回退的完整构建" >&2; exit 1; }
    fingerprint="$(cat "$frontend/$dist/.quant-source-sha")"
    mode="production"
elif [ "$mode" = "dev" ]; then
    dist=".next-dev"
else
    dist=".next-release-${fingerprint:0:16}"
fi
pid="$(port_pid)"
if [ -n "$pid" ] && healthy && [ "$action" != "--rollback" ] && [ "$(field mode)" = "$mode" ] && { [ "$mode" = "dev" ] || [ "$(field fingerprint)" = "$fingerprint" ]; }; then
    echo "前端已就绪，复用正在运行的${mode}服务";exit 0
fi
# 构建先完成，再切换进程；失败不会停止原前端。
if [ "$mode" != "dev" ] && [ "$action" != "--rollback" ]; then
    if [ ! -f "$dist/BUILD_ID" ] || [ "$(cat "$dist/.quant-source-sha" 2>/dev/null || true)" != "$fingerprint" ]; then
        echo "源码变化，生成独立生产构建${dist}（保留原构建）"
        QUANT_NEXT_DIST_DIR="$dist" node node_modules/next/dist/bin/next build
        node - "$dist" <<'JS'
const fs=require('fs');const file='tsconfig.json';const config=JSON.parse(fs.readFileSync(file,'utf8'));const dist=process.argv[2];
config.include=(config.include||[]).filter(v=>!v.startsWith('.next-release-')||v===dist+'/types/**/*.ts');
fs.writeFileSync(file,JSON.stringify(config,null,2)+'\n');
JS
        printf '%s' "$fingerprint" > "$dist/.quant-source-sha"
    else echo "复用已验证的生产构建$dist"; fi
fi
if [ -n "$pid" ]; then
    known="$(cat "$logs/frontend.pid" 2>/dev/null || true)"
    if [ "$known" != "$pid" ]; then echo "3000端口由其他进程占用，不终止未知进程" >&2;exit 1;fi
    if launchctl print "gui/$(id -u)/com.quantcopilot.frontend" >/dev/null 2>&1; then
        launchctl remove com.quantcopilot.frontend
    else kill -TERM "$pid"; fi
    for n in {1..20}; do [ -z "$(port_pid)" ] && break;sleep .25;done
    [ -z "$(port_pid)" ] || { echo "原前端仍在退出，暂不覆盖" >&2;exit 1; }
fi
if [ "$mode" = "dev" ]; then command="dev";else command="start";fi
if [ "$(uname)" = "Darwin" ]; then
    # 由launchd托管，启动终端或应用退出后不会带走前端进程。
    launchctl remove com.quantcopilot.frontend >/dev/null 2>&1 || true
    launchctl submit -l com.quantcopilot.frontend -o "$logs/next.log" -e "$logs/next.log" -- /usr/bin/env QUANT_NEXT_DIST_DIR="$dist" NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" "$(command -v node)" "$frontend/node_modules/next/dist/bin/next" "$command" "$frontend" -p 3000
    child=""
else
    nohup env QUANT_NEXT_DIST_DIR="$dist" NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" node node_modules/next/dist/bin/next "$command" -p 3000 > "$logs/next.log" 2>&1 < /dev/null &
    child=$!
fi
ready=0
for n in {1..45}; do
    if healthy; then ready=1;break;fi
    if [ -n "$child" ]; then kill -0 "$child" 2>/dev/null || break; fi
    sleep 1
done
if [ "$ready" != "1" ]; then echo "前端未就绪，请检查$logs/next.log；旧构建保留在$previous" >&2;exit 1;fi
printf '%s' "$(port_pid)" > "$logs/frontend.pid"
node - "$manifest" "$dist" "$previous" "$mode" "$fingerprint" <<'JS'
const fs=require('fs');const [file,dist,previous,mode,fingerprint]=process.argv.slice(2);
const data={dist,previous:previous===dist?'':previous,mode,fingerprint,ready_at:new Date().toISOString()};
fs.writeFileSync(file+'.tmp',JSON.stringify(data));fs.renameSync(file+'.tmp',file);
JS
echo "前端就绪：$mode / $dist"
