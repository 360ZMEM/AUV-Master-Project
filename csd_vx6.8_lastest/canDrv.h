/**
    @file       canDrv.h
    @brief      VxWorks下can驱动程序
    @copyright  senbo
    @author     nick.xu
    @version    V1.0
    @date       2018.04.12 V1.0 创建
    @note       程序用来实现can驱动, 支持sja100芯片或逻辑
*/

#ifndef CANDRV_H
#define CANDRV_H

#include "sjaDrv.h"

#define MAX_CAN_DEVICE      (2)
#define MAX_SJA_DEVICE      (8)

#define ISA_CAN              0
#define LS_2K_CAN               1

/* enum  SJA baudrate */
#define	    BAUD_1000K      1
#define		BAUD_800K 	    2
#define		BAUD_500K       3
#define		BAUD_320K       4
#define		BAUD_250K       5
#define		BAUD_160K       6
#define		BAUD_125K       7
#define		BAUD_100K       8
#define		BAUD_80K        9

#define     SINGLE_POINT    0
#define     TRI_POINT       1
#define     FRAME_SFF       0
#define     FRAME_EFF       1
#define     FRAME_SFF_MASK  0x7FF
#define     FRAME_EFF_MASK  0x1FFFFFFF
typedef struct SjaFrame_s
{
    unsigned char frame_type;
	unsigned char frame_dlc;
    unsigned int  frame_id;
	unsigned char frame_data[8];
} SjaFrame_t;

typedef struct CanResource_s
{
    int base;
    int isr_base;
    int irq;
    int nchannel;
    int dev_stride;
	int board_id;
} CanResource_t;

#ifdef __cplusplus
extern "C" {
#endif

int CanDrv();
int can_create(CanResource_t *pCR);
int can_remove(int fd);
void can_intr(int arg);

#ifdef __cplusplus
}
#endif

#endif
