/********************************************************************
文件名称:   mspCom.h

文件功能:   定义扩展串口板卡资源等信息 文件支持多种串口卡

文件说明:   当没有库文件源代码时 修改此文件宏没有意义

当前版本:   V1.1

修改记录:   2010-10-19  V1.0    徐佳谋  创建
            2013-10-08  V1.1    徐佳谋  升级    参考CSD驱动升级MSP驱动
			2017-12-30  V1.2    李世杰  升级    添加EMM8P支持
********************************************************************/
#ifndef _MSPCOM_H_
#define _MSPCOM_H_

#include "drv/sio/i8250Sio.h"

#ifndef _I8250_
#define _I8250_

/* 串口配置参数 */
typedef struct
{
    USHORT vector;      /* 中断向量 */
    ULONG  baseAdrs;    /* 寄存器基地址 */
    USHORT regSpace;    /* 寄存器间隔 */
    USHORT intLevel;    /* 中断IRQ */
	unsigned char com_mode;
} I8250_CHAN_PARAS;

/* 串口信息 */
typedef struct 
{
    unsigned short ushBase; /* 串口基地址 */
    int irq;                /* 串口使用中断 */
	unsigned char com_mode;
}com_info_t;

/* defines */
#define UART_REG(reg,chan) (devParas[chan].baseAdrs + reg*devParas[chan].regSpace)
#define UART_REG_ADDR_INTERVAL  1   /* address diff of adjacent regs. */

#define INT_NUM_IRQ0        0x20                    /* 此处注意当不是使用PIC模式时需要修改 */
#define INT_VEC_GET(irq)    (INT_NUM_IRQ0 + irq)

/* 串口个数 */
#define N_MSPCOM_CHANNELS   8

#define CFG_COM_232         0
#define CFG_COM_422			1
#define CFG_COM_485_ECHO    2
#define CFG_COM_485_NOECHO  3

/* FIFO MAX */
#define FIFO_MAX_BYTE       16
#define FIFO_HALF_BYTE      (FIFO_MAX_BYTE / 2)

/* FIFO Control Register */
#define FCR_EN              0x01        /* FIFO Enable */
#define FIFO_ENABLE         FCR_EN
#define FCR_RXCLR           0x02        /* Rx FIFO Clear */
#define RxCLEAR             FCR_RXCLR
#define FCR_TXCLR           0x04        /* Tx FIFO Clear */
#define TxCLEAR             FCR_TXCLR
#define FCR_DMA             0x08        /* FIFO Mode Control */
#define FCR_TXTRIG_L        0x10        /* TX FIFO Trigger level Low */
#define FCR_TXTRIG_H        0x20        /* TX FIFO Trigger level High */
#define FCR_RXTRIG_L        0x40        /* FIFO Trigger level Low */
#define FCR_RXTRIG_H        0x80        /* FIFO Trigger level High */

/* LCR DLAB */
#define LCR_DLAB            0x80

/* Enable Enhanced Registers */
#define ER_EN               0xBF        /* LCR=0xBF */

/* Enhanced Function Reg */
#define EF_EN               0x10        /* Enhanced Function Bits Enable */
#endif

/* 板卡寄存器地址 */
#define MSP_BOARD_ISR_REG   0x02    /* 板卡上中断状态寄存器 */
#define MSP_ISR_REG_MASK    0xFF    /* 中断状态寄存器值屏蔽码 */

void mspComInt(int offset);
SIO_CHAN *mspSerialChanGet(int channel);
int mspSerialHwInit(unsigned short ushBase, int offset, com_info_t *pInfo);

extern BOOL sysBp;          /* TRUE for BP, FALSE for AP */

#endif
