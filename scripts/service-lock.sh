#!/bin/bash
# 仅串行化同一项目的启动；不终止未知进程。过期锁须确认原PID已退出。
quant_lock_acquire(){
    quant_lock_dir="$1"
    local waited=0 owner=""
    while ! mkdir "$quant_lock_dir" 2>/dev/null; do
        owner="$(cat "$quant_lock_dir/pid" 2>/dev/null || true)"
        if [[ "$owner" =~ ^[0-9]+$ ]] && ! kill -0 "$owner" 2>/dev/null; then
            rm -f "$quant_lock_dir/pid";rmdir "$quant_lock_dir" 2>/dev/null || true
        elif [ -z "$owner" ] && [ "$waited" -ge 25 ]; then
            rmdir "$quant_lock_dir" 2>/dev/null || true
        fi
        [ "$waited" -lt 600 ] || { echo "启动锁仍被占用，请稍后重试：$quant_lock_dir" >&2;return 1; }
        sleep .2;waited=$((waited+1))
    done
    printf '%s' "$$" > "$quant_lock_dir/pid"
    trap quant_lock_release EXIT
    trap 'exit 130' INT TERM HUP
}
quant_lock_release(){
    if [ "$(cat "$quant_lock_dir/pid" 2>/dev/null || true)" = "$$" ]; then
        rm -f "$quant_lock_dir/pid";rmdir "$quant_lock_dir" 2>/dev/null || true
    fi
}
