#!/bin/bash
# 生产构建先完成再切换，启动失败自动恢复原完整构建；同项目启动串行化。
set -e
project="$(cd "$(dirname "$0")/.." && pwd)"
frontend="$project/frontend"
logs="$project/backend/logs"
manifest="$logs/frontend-release.json"
mkdir -p "$logs"
source "$project/scripts/service-lock.sh"
quant_lock_acquire "$logs/frontend-start.lock"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"
mode="${QUANT_FRONTEND_MODE:-production}"
action="${1:-start}"
port="${QUANT_FRONTEND_PORT:-3000}"
wait_seconds="${QUANT_FRONTEND_READY_SECONDS:-45}"
label="com.quantcopilot.frontend"
[ "$port" = "3000" ] || label="$label.$port"
cd "$frontend"
healthy(){ curl -fsS --max-time 3 "http://127.0.0.1:$port/invest" >/dev/null 2>&1; }
port_pid(){ lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true; }
field(){ node -e 'try{const v=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));console.log(v[process.argv[2]]||"")}catch{}' "$manifest" "$1"; }
fingerprint="$(node scripts/source-fingerprint.mjs)"
previous="$(field dist)"
previous_mode="$(field mode)"
if [ "$action" = "--rollback" ]; then
    dist="$(field previous)"
    [ -n "$dist" ] && [ -f "$frontend/$dist/BUILD_ID" ] || { echo "没有可回退的完整构建" >&2;exit 1; }
    fingerprint="$(cat "$frontend/$dist/.quant-source-sha")";mode="production"
elif [ "$mode" = "dev" ]; then dist=".next-dev"
else dist=".next-release-${fingerprint:0:16}";fi
pid="$(port_pid)"
known="$(cat "$logs/frontend.pid" 2>/dev/null || true)"
if [ -n "$pid" ] && [ "$known" = "$pid" ] && healthy && [ "$action" != "--rollback" ] && [ "$(field mode)" = "$mode" ] && { [ "$mode" = "dev" ] || [ "$(field fingerprint)" = "$fingerprint" ]; }; then
    echo "前端已就绪，复用正在运行的${mode}服务";exit 0
fi
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
    else echo "复用已验证的生产构建${dist}";fi
fi
if [ -n "$pid" ]; then
    known="$(cat "$logs/frontend.pid" 2>/dev/null || true)"
    [ "$known" = "$pid" ] || { echo "$port端口由其他进程占用，不终止未知进程" >&2;exit 1; }
    if launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then launchctl remove "$label"
    else kill -TERM "$pid";fi
    for n in {1..20};do [ -z "$(port_pid)" ] && break;sleep .25;done
    [ -z "$(port_pid)" ] || { echo "原前端仍在退出，暂不覆盖" >&2;exit 1; }
fi

launch_runtime(){
    local target="$1" target_mode="$2" command="start" n child=""
    [ "$target_mode" != "dev" ] || command="dev"
    if [ "$(uname)" = "Darwin" ]; then
        launchctl remove "$label" >/dev/null 2>&1 || true
        launchctl submit -l "$label" -o "$logs/next.log" -e "$logs/next.log" -- /usr/bin/env QUANT_NEXT_DIST_DIR="$target" NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" "$(command -v node)" "$frontend/node_modules/next/dist/bin/next" "$command" "$frontend" -p "$port" || return 1
    else
        nohup env QUANT_NEXT_DIST_DIR="$target" NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" node node_modules/next/dist/bin/next "$command" -p "$port" > "$logs/next.log" 2>&1 < /dev/null &
        child=$!
    fi
    for ((n=0;n<wait_seconds;n++)); do
        if healthy;then printf '%s' "$(port_pid)" > "$logs/frontend.pid";return 0;fi
        if [ -n "$child" ];then kill -0 "$child" 2>/dev/null || break;fi
        sleep 1
    done
    if [ "$(uname)" = "Darwin" ];then launchctl remove "$label" >/dev/null 2>&1 || true
    elif [ -n "$child" ];then kill -TERM "$child" 2>/dev/null || true;fi
    return 1
}
if ! launch_runtime "$dist" "$mode";then
    cp "$logs/next.log" "$logs/next-failed.log" 2>/dev/null || true
    echo "新前端启动失败，尝试恢复原构建；详情见 $logs/next-failed.log" >&2
    if [ -n "$previous" ] && [ -f "$frontend/$previous/BUILD_ID" ] && launch_runtime "$previous" "production";then
        # 原manifest未被覆盖，恢复后的PID更新；错误仍返回非零，不能冒充升级成功。
        echo "已自动恢复原构建：$previous" >&2
    else echo "自动恢复未成功，完整构建仍保留，请检查日志" >&2;fi
    exit 1
fi
node - "$manifest" "$dist" "$previous" "$mode" "$fingerprint" <<'JS'
const fs=require('fs');const [file,dist,previous,mode,fingerprint]=process.argv.slice(2);
const data={dist,previous:previous===dist?'':previous,mode,fingerprint,ready_at:new Date().toISOString()};
fs.writeFileSync(file+'.tmp',JSON.stringify(data));fs.renameSync(file+'.tmp',file);
JS
echo "前端就绪：$mode / $dist"
