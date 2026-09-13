#!/bin/bash
# 归属化清理:仅删除本任务创建的资源(按标签与命名),禁止全局清理
TASK_LABEL='task=sku-delivery-r2-v4-r1'
echo '[1/3] 删除任务容器(按标签)'
for C in $(sudo docker ps -a --filter "label=$TASK_LABEL" --format '{{.Names}}'); do sudo docker rm -f $C; done
echo '[2/3] 删除任务卷(按命名 sku-r2-*)'
for V in $(sudo docker volume ls --format '{{.Name}}' | grep -E '^sku-r2-'); do sudo docker volume rm $V; done
echo '[3/3] 共享镜像处理:postgres:15-alpine、redis:7-alpine 为任务启动前已存在的共享缓存'
echo '      → 按授权保留,不删除、不 prune、不强制清理(记录:引用≠独占)'
echo 'cleanup 完成(未使用 docker system prune)'
