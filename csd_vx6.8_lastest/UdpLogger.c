/*
 * @file    UdpLogger.c
 * @brief   UDP 日志重定向模块 - VxWorks 实现
 *
 * 将 printf 输出通过环形缓冲区暂存, 由低优先级后台任务异步通过 UDP 发送到上位机。
 *
 * 架构:
 *   [调用者任务] --intLock--> [环形缓冲区 rngBuf] --taskDelay--> [UdpLoggerTask] --> UDP sendto
 *
 * 特性:
 *   - 多任务安全 (intLock/intUnlock 极短临界区)
 *   - 非阻塞写入 (缓冲区满则丢弃, 不影响调用者实时性)
 *   - 安全降级 (模块未初始化时, 直接调用原始 printf 到串口)
 *   - 异步发送 (不在调用者上下文做网络操作)
 */

#include <vxWorks.h>
#include <taskLib.h>
#include <rngLib.h>
#include <sockLib.h>
#include <inetLib.h>
#include <stdarg.h>
#include <string.h>
#include <stdio.h>
#include <intLib.h>
#include <sysLib.h>
#include <netinet/in.h>

#include "UdpLogger.h"

/*==========================================================================
 * 模块内部状态
 *==========================================================================*/

static RING_ID  g_logRingBuf  = NULL;   /* 环形缓冲区句柄 */
static int      g_logSockFd   = -1;     /* UDP socket fd   */
static int      g_logInited   = 0;      /* 初始化完成标志  */
static struct sockaddr_in g_logDestAddr; /* 目标地址       */

/* 溢出统计 (调试用) */
static unsigned long g_logDropCount = 0;

/*==========================================================================
 * 内部函数声明
 *==========================================================================*/
static void UdpLoggerTask(void);

/*==========================================================================
 * 公共接口实现
 *==========================================================================*/

/**
 * UdpLogger_Init - 初始化 UDP 日志模块
 *
 * 必须在 ipAttach/ifconfig 之后调用。
 */
void UdpLogger_Init(void)
{
    /* 防止重复初始化 */
    if (g_logInited)
        return;

    /* 1. 创建环形缓冲区 */
    g_logRingBuf = rngCreate(UDP_LOG_BUF_SIZE);
    if (g_logRingBuf == NULL)
    {
        /* 降级: 无缓冲区则模块不启用, printf 保持原始行为由宏处理 */
        return;
    }

    /* 2. 创建 UDP socket */
    g_logSockFd = socket(AF_INET, SOCK_DGRAM, 0);
    if (g_logSockFd < 0)
    {
        rngDelete(g_logRingBuf);
        g_logRingBuf = NULL;
        return;
    }

    /* 3. 配置目标地址 */
    memset(&g_logDestAddr, 0, sizeof(g_logDestAddr));
    g_logDestAddr.sin_family      = AF_INET;
    g_logDestAddr.sin_port        = htons(UDP_LOG_PORT);
    g_logDestAddr.sin_addr.s_addr = inet_addr(UDP_LOG_TARGET_IP);

    /* 4. 标记初始化完成 */
    g_logInited = 1;

    /* 5. 创建后台发送任务 */
    taskSpawn("tUdpLog",            /* 任务名       */
              UDP_LOG_TASK_PRI,     /* 优先级       */
              0,                    /* 选项         */
              UDP_LOG_TASK_STACK,   /* 堆栈大小     */
              (FUNCPTR)UdpLoggerTask,
              0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
}

/**
 * udp_log_printf - printf 替代, 写入环形缓冲区
 *
 * 如果模块未初始化, 降级到原始 printf (串口输出)。
 */
int udp_log_printf(const char *fmt, ...)
{
    va_list ap;
    char    buf[256];   /* 单次 printf 最大长度 */
    int     len;
    int     lockKey;
    int     nWritten;

    va_start(ap, fmt);
    len = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

    if (len <= 0)
        return len;

    /* 截断保护 */
    if (len >= (int)sizeof(buf))
        len = sizeof(buf) - 1;

    /* 模块未初始化 -> 降级到原始串口 printf */
    if (!g_logInited)
    {
        /* 直接调用底层写函数避免宏递归 */
        write(1, buf, len);  /* fd=1 即 stdout/console */
        return len;
    }

    /* 写入环形缓冲区 (intLock 极短临界区, 保证多任务安全) */
    lockKey = intLock();
    nWritten = rngBufPut(g_logRingBuf, buf, len);
    intUnlock(lockKey);

    /* 统计丢弃 */
    if (nWritten < len)
        g_logDropCount++;

    return nWritten;
}

/*==========================================================================
 * 后台发送任务
 *==========================================================================*/

/**
 * UdpLoggerTask - 周期性从环形缓冲区取数据并 UDP 发送
 *
 * 优先级低 (200), 每 UDP_LOG_FLUSH_MS 毫秒唤醒一次。
 * 每次最多发送 UDP_LOG_MTU 字节 (一个 UDP 包)。
 */
static void UdpLoggerTask(void)
{
    char    sendBuf[UDP_LOG_MTU];
    int     nBytes;
    int     ticksDelay;

    /* 计算延迟 tick 数 (sysClkRate ticks/sec) */
    ticksDelay = (sysClkRateGet() * UDP_LOG_FLUSH_MS) / 1000;
    if (ticksDelay < 1)
        ticksDelay = 1;

    for (;;)
    {
        /* 休眠等待数据积累 */
        taskDelay(ticksDelay);

        /* 循环发送直到缓冲区空 */
        while ((nBytes = rngBufGet(g_logRingBuf, sendBuf, UDP_LOG_MTU)) > 0)
        {
            sendto(g_logSockFd,
                   sendBuf,
                   nBytes,
                   0,
                   (struct sockaddr *)&g_logDestAddr,
                   sizeof(g_logDestAddr));
        }
    }
}
