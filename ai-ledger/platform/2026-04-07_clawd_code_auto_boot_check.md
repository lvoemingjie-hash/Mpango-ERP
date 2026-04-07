# Linux 系统自动开机设置检查报告

> **检查时间：** 2026-04-07 06:10 CST  
> **检查工具：** Clawd Code  
> **目标系统：** 当前 Linux 主机  

---

## 1. 检查 RTC（实时时钟）闹钟状态

### 命令
```bash
cat /proc/driver/rtc
```

### 输出
```
rtc_time        : 06:10:15
rtc_date        : 2026-04-07
alrm_time       : 00:35:00
alrm_date       : 2026-04-08
alarm_IRQ       : yes
alrm_pending    : no
update IRQ enabled   : no
periodic IRQ enabled : no
periodic IRQ frequency: 1024
max user IRQ frequency: 64
24hr            : yes
periodic_IRQ    : no
update_IRQ      : no
HPET_emulated   : yes
BCD             : yes
DST_enable      : no
periodic_freq   : 1024
batt_status     : okay
```

### 分析结论

| 项目 | 值 | 说明 |
|------|-----|------|
| 当前 RTC 时间 | 2026-04-07 06:10:15 | 系统实时时钟正常 |
| **闹钟时间** | **2026-04-08 00:35:00** | ⚠️ **已设置 RTC 闹钟，计划于明天 00:35 触发** |
| alarm_IRQ | yes | 闹钟中断已启用 |
| alrm_pending | no | 闹钟当前未处于挂起状态（尚未触发） |
| batt_status | okay | 主板电池状态正常 |

> **⚠️ 重要发现：** RTC 硬件闹钟已设置，将于 **2026-04-08 00:35:00** 触发。如果 BIOS 中启用了 "Resume by Alarm" / "RTC Alarm Wake" 功能，系统将在该时间点自动开机。

---

## 2. 检查 RTC wakealarm 文件

### 命令
```bash
cat /sys/class/rtc/rtc0/wakealarm
```

### 输出
```
1775608500
```

### 分析结论

| 项目 | 值 | 说明 |
|------|-----|------|
| wakealarm 时间戳 | 1775608500 | Unix 时间戳 |
| 对应时间 | **2026-04-08 08:35:00 CST** | ⚠️ 与 RTC 闹钟日期一致 |

> **说明：** `/sys/class/rtc/rtc0/wakealarm` 中设置的唤醒时间与 `/proc/driver/rtc` 中的闹钟信息一致（差异仅在于时区显示，wakealarm 使用 UTC+8，RTC alrm_time 显示的 `00:35` 可能是 UTC 时间，对应 CST 08:35）。
>
> 该值可通过 `echo 0 > /sys/class/rtc/rtc0/wakealarm` 清除。

---

## 3. 检查 systemd 定时器（wake/boot/power 相关）

### 命令
```bash
systemctl list-timers --all | grep -i -E 'wake|boot|power'
```

### 输出
```
（无输出，exit code: 1）
```

### 分析结论

**未发现** 与唤醒（wake）、开机（boot）或电源管理（power）相关的 systemd 定时器。系统层级的定时开机任务并非通过 systemd timer 管理。

---

## 4. 检查当前用户 crontab

### 命令
```bash
crontab -l
```

### 输出
```
# Backup every day at 2:00 AM
0 2 * * * /home/ivy/.openclaw/backup.sh >> /home/ivy/.openclaw/backups/backup.log 2>&1

# Intelligent check - only when necessary (every 24 hours)
0 10 * * * /home/ivy/.openclaw/intelligent-check.sh >> /home/ivy/.openclaw/backups/intelligent-check.log 2>&1

# Weekly maintenance on Sunday at 3:00 AM
0 3 * * 0 /home/ivy/.openclaw/maintenance-weekly.sh >> /home/ivy/.openclaw/backups/maintenance.log 2>&1
```

### 分析结论

crontab 中共有 3 条定时任务，均为**常规运维任务**，与自动开机无关：

| 任务 | 时间 | 脚本 | 用途 |
|------|------|------|------|
| 每日备份 | 每天 02:00 | `backup.sh` | 数据备份 |
| 智能检查 | 每天 10:00 | `intelligent-check.sh` | 系统健康检查 |
| 周维护 | 每周日 03:00 | `maintenance-weekly.sh` | 周度维护 |

> **结论：** crontab 中**没有**设置自动开机相关的任务。

---

## 5. 检查 at 队列（一次性定时任务）

### 命令
```bash
atq
```

### 输出
```
/bin/sh: 1: atq: not found
```

### 分析结论

系统**未安装** `at` 服务（`atd`），因此不存在通过 `at` 调度的一次性定时任务。此路径可排除。

---

## 📋 综合结论

| 检查项 | 是否存在自动开机设置 | 详情 |
|--------|----------------------|------|
| RTC 硬件闹钟 (`/proc/driver/rtc`) | ⚠️ **是** | 闹钟设于 **2026-04-08 00:35:00 (UTC) / 08:35:00 (CST)**，alarm_IRQ 已启用 |
| wakealarm (`/sys/class/rtc/rtc0/wakealarm`) | ⚠️ **是** | 时间戳 1775608500 = 2026-04-08 08:35 CST |
| systemd timers | ✅ 否 | 无 wake/boot/power 相关定时器 |
| crontab | ✅ 否 | 仅有备份、检查、维护等常规任务 |
| at 队列 | ✅ 否 | `at` 服务未安装 |

### 🔴 总结

**当前系统存在 RTC 硬件闹钟自动开机设置。** RTC 闹钟已配置于 **2026-04-08 08:35:00 CST** 触发，若 BIOS/UEFI 中启用了 "Resume by Alarm" 或 "RTC Wake" 功能，系统将在该时间自动开机。

### 🛠️ 如需取消自动开机

```bash
# 方法 1：清零 wakealarm
sudo sh -c 'echo 0 > /sys/class/rtc/rtc0/wakealarm'

# 方法 2：禁用硬件 RTC 闹钟
sudo hwclock --hctosys  # 同步时钟（可选）

# 方法 3：进入 BIOS/UEFI，关闭 "Resume by Alarm" / "Wake on RTC" 选项
```

---

*报告生成完毕。*
