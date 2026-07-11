/*
 * @file    UdpLogger.h
 * @brief   UDP 日志重定向模块 - 配置与接口声明
 *
 * 将 VxWorks printf 输出通过 UDP 发送到上位机 (PC/Jetson)。
 * 使用方法:
 *   1. 在 usrAppInit.c 网络初始化后调用 UdpLogger_Init()
 *   2. 在 AgreedTerms.h 中 #define printf udp_log_printf
 *   3. PC 端运行 scripts/log_receiver.py 接收日志
 *
 * IP 与协议包相同 (192.168.0.11), 端口区分:
 *   - 52364: 下行控制包 (AMD -> VxWorks)
 *   - 52365: 上行状态包 (VxWorks -> AMD)
 *   - 52366: Sniffer 镜像
 *   - 52367: UDP 日志 (本模块)
 */

#ifndef _UDP_LOGGER_H
#define _UDP_LOGGER_H

#ifdef __cplusplus
extern "C" {
#endif

/*==========================================================================
 * 配置参数 (可根据实际网络环境修改)
 *==========================================================================*/

/* 目标 IP: 上位机 (PC/Jetson) 地址, 与协议包目标一致 */
#define UDP_LOG_TARGET_IP       "192.168.0.11"

/* 日志 UDP 端口 (区别于协议端口 52364/52365/52366) */
#define UDP_LOG_PORT            52367

/* 环形缓冲区大小 (字节) - 用于暂存 printf 产生的文本 */
#define UDP_LOG_BUF_SIZE        8192

/* 单个 UDP 包最大有效载荷 (避免分片, 小于 MTU) */
#define UDP_LOG_MTU             1400

/* 发送任务刷新周期 (ms) - 控制日志延迟 vs CPU 负载 */
#define UDP_LOG_FLUSH_MS        50

/* 发送任务优先级 (较低, 不影响控制回路) */
#define UDP_LOG_TASK_PRI        200

/* 发送任务堆栈大小 */
#define UDP_LOG_TASK_STACK      4096

/*==========================================================================
 * 公共接口
 *==========================================================================*/

/**
 * @brief 初始化 UDP 日志模块
 *
 * 创建环形缓冲区和发送任务。必须在网络 (ipAttach/ifconfig) 初始化之后调用。
 * 初始化完成前的 printf 仍走原始串口输出 (安全降级)。
 */
void UdpLogger_Init(void);

/**
 * @brief printf 替代函数 - 将格式化文本写入环形缓冲区
 *
 * @param fmt   printf 格式字符串
 * @param ...   可变参数
 * @return      写入的字节数, 或 -1 (模块未初始化时降级到原始 printf)
 *
 * 多任务安全 (intLock 短临界区保护)。
 * 如果环形缓冲区满, 新数据将被丢弃 (不阻塞调用者)。
 */
int udp_log_printf(const char *fmt, ...);

#ifdef __cplusplus
}
#endif

#endif /* _UDP_LOGGER_H */
