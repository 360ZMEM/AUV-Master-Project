/********************************************************************
文件名称:   dtp.h

文件功能:   VxWorks功能测试函数头文件

文件说明:   定义一些宏和结构体

当前版本:   V1.9

修改记录:   2010-10-12  V1.0    徐佳谋  创建
            2012-03-31  V1.1    徐佳谋  升级    增加各种测试函数
            2012-04-18  V1.2    王鹤翔  升级    增加扬声器测试函数
            2012-04-26  V1.3    徐佳谋  升级    增加网络广播包测试
            2012-09-04  V1.4    徐佳谋  升级    增加串口查询发送函数
            2012-12-19  V1.5    徐佳谋  升级    增加双网切换测试函数
            2013-04-27  V1.6    徐佳谋  升级    增加TCP性能测试
            2013-06-07  V1.7    徐佳谋  升级    增加VxWorks6.8支持
            2013-06-27  V1.8    徐佳谋  升级    增加液晶屏背光控制
            2013-11-06  V1.9    徐佳谋  升级    增加调试开关
********************************************************************/

#define INCLUDE_WINDML_TEST     0       /* WindML测试 1:包含 0:不包含 */
#define INCLUDE_COM_TIMEOUT     0       /* 串口超时接收功能 1:使用 0:不使用 */
#define INCLUDE_NET_SWITCH      0       /* 双网卡切换测试 1:包含 0:不包含 */

#define COM_BAUD_RATE           115200  /* 串口波特率 */
#define UDP_SERVER_TID          0       /* UDP服务器任务索引 */
#define TCP_SERVER_TID          4       /* TCP服务器任务索引 */
#define UDP_GROUP_TID           8       /* UDP组播任务索引 */
#define UDP_BROADCAST_TID       12      /* UDP组播任务索引 */
#define TCP_PERFORM_TID         16      /* TCP性能任务索引 */
#define UDP_SERVER_PORT         1984    /* UDP服务器使用端口号 */
#define UDP_CLIENT_PORT         1986    /* UDP客户端使用端口号 */
#define TCP_SERVER_PORT         1988    /* TCP服务器使用端口号 */
#define TCP_CLIENT_PORT         1990    /* TCP客户端使用端口号 */
#define UDP_GROUP_PORT          1992    /* UDP组播使用端口号 */
#define UDP_BROADCAST_PORT      1994    /* UDP广播使用端口号 */

#define UDP_GROUP_ADDRESS1      "224.1.1.1" /* UDP组播地址1 */
#define UDP_GROUP_ADDRESS2      "224.1.1.2" /* UDP组播地址2 */

#define UDP_BROADCAST_ADDRESS   "255.255.255.255"       /* UDP广播地址 */

#define TCP_PERFORMANCE_SIZE    (200 * 1024 * 1024)     /* TCP性能测试总数据量 */

#define INT_NUM_IRQ0            0x20                    /* 此处注意当不是使用PIC模式时需要修改 */
#define INT_VEC_GET(irq)        (INT_NUM_IRQ0 + irq)

#define BOARD_CPU_FREQUENCE     (500000000L)            /* LX3160:500MHz PM4060:800MHZ ~ 1.4MHZ */

#define LPT_BASE_ADDRESS        0x378       /* 并口基地址 */

#define DMA_BUFFER_ADDR         0x200000    /* 使用的DMA物理地址 */
#define DMA_BUFFER_SIZE         0x10000     /* DMA缓冲区最大长度 */

#define DMAC0_BASE              0x00                                /* DMA0控制器基址寄存器 */
#define DMAC0_CH_CA(channel)    (DMAC0_BASE + (channel << 1))       /* 通道0-3当前地址寄存器 */
#define DMAC0_CH_CC(channel)    (DMAC0_BASE + (channel << 1) + 1)   /* 通道0-3当前字节计数寄存器 */

#define DMAC0_STATUS_CMD        (DMAC0_BASE + 8)     /* 状态/命令寄存器 */
#define DMAC0_REQUEST           (DMAC0_BASE + 9)     /* 请求寄存器 */
#define DMAC0_MASK              (DMAC0_BASE + 10)    /* 屏蔽寄存器 */
#define DMAC0_MODE              (DMAC0_BASE + 11)    /* 模式寄存器 */
#define DMAC0_CLEAR_FF          (DMAC0_BASE + 12)    /* 清除先后触发器寄存器 */
#define DMAC0_CLEAR_ALL         (DMAC0_BASE + 13)    /* 主清除寄存器 */
#define DMAC0_CLEAR_MASK        (DMAC0_BASE + 14)    /* 清除屏蔽寄存器 */
#define DMAC0_MAKK_ALL          (DMAC0_BASE + 15)    /* 多通道清除屏蔽寄存器 */

#define DMAC1_BASE              0xC0                                    /* DMA1控制器基址寄存器 */
#define DMAC1_CH_CA(channel)    (DMAC1_BASE + ((channel - 4) << 2))     /* 通道4-7当前地址寄存器 */
#define DMAC1_CH_CC(channel)    (DMAC1_BASE + ((channel - 4) << 2) + 2) /* 通道4-7当前字节计数寄存器 */

#define DMAC1_STATUS_CMD        (DMAC1_BASE + 16)    /* 状态/命令寄存器 */
#define DMAC1_REQUEST           (DMAC1_BASE + 18)    /* 请求寄存器 */
#define DMAC1_MASK              (DMAC1_BASE + 20)    /* 屏蔽寄存器 */
#define DMAC1_MODE              (DMAC1_BASE + 22)    /* 模式寄存器 */
#define DMAC1_CLEAR_FF          (DMAC1_BASE + 24)    /* 清除先后触发器寄存器 */
#define DMAC1_CLEAR_ALL         (DMAC1_BASE + 26)    /* 主清除寄存器 */
#define DMAC1_CLEAR_MASK        (DMAC1_BASE + 28)    /* 清除屏蔽寄存器 */
#define DMAC1_MAKK_ALL          (DMAC1_BASE + 30)    /* 多通道清除屏蔽寄存器 */

#define DMA_MODE_DEMAND         0x00
#define DMA_MODE_SINGLE         0x40
#define DMA_MODE_BLOCK          0x80
#define DMA_MODE_CASCADE        0xc0
#define DMA_MODE_DECREMENT      0x20
#define DMA_MODE_INCREMENT      0x00
#define DMA_MODE_AUTO_ENABLE    0x10
#define DMA_MODE_AUTO_DISABLE   0x00
#define DMA_MODE_WRITE          0x04
#define DMA_MODE_READ           0x08

#define DMA_CMD_DACK_H          0x80
#define DMA_CMD_DACK_L          0x00
#define DMA_CMD_DREQ_H          0x00
#define DMA_CMD_DREQ_L          0x40
#define DMA_CMD_MEM_ENABLE      0x01
#define DMA_CMD_MEM_DISABLE     0x00

#define BCD_TO_BIN(x) (((x) & 0x0F) + (((x) >> 4) * 10))
#define BIN_TO_BCD(x) ((((x) / 10) << 4) + ((x) % 10))

#define RTC_INDEX       0x70
#define RTC_DATA        0x71
#define RTC_CENTURY     0x32
#define RTC_YEAR        0x09
#define RTC_MONTH       0x08
#define RTC_DAY         0x07
#define RTC_HOUR        0x04
#define RTC_MINUTE      0x02
#define RTC_SECOND      0x00

#define TIMER0          0x40
#define TIMER1          0x41
#define TIMER2          0x42
#define TIMER2_GATE     0x61
#define TIMER_CONTROL   0x43

#define CLOCK           1193181
