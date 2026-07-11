/*
 * @Author: lisj
 * @Date: 2019-11-27 11:09:07
 * @LastEditTime: 2019-11-27 13:54:04
 * @LastEditors: lisj
 * @Description: CAN 设备通用测试程序
 */
#include "fcntl.h"
#include "in.h"
#include "inetLib.h"
#include "ioLib.h"
#include "iv.h"
#include "logLib.h"
#include "sioLib.h"
#include "sockLib.h"
#include "stdio.h"
#include "string.h"
#include "taskLib.h"
#include "tickLib.h"
#include "unistd.h"
#include "vxWorks.h"

#include "canDrv.h"

static int GetKeyInput(int radix);
static int init_can = 0;
char *Can_name[] = {"/can0/0", "/can0/1"};

int fd_can[2] = {0, 0};

/**
 * @函数名: CreatCanDrv
 * @参数: 无
 * @返回值: 无
 * @函数描述: can初始化例程
 */
void CreatCanDrv(void) {
    CanResource_t cr;     /* can设备使用的初始化需要资源结构体 */
    cr.base = 0xD0000; /* 第一路can的基地址 */
    cr.dev_stride = 0x4000;   /* 每路can设备 地址步进长度 */
    cr.irq = 10;              /* can设备使用的中断号 */
    cr.isr_base = 0x302; /* can设备的中断状态寄存器地址 基地址偏移2 */
    cr.nchannel = 2;          /* can设备个数 */
    cr.board_id = ISA_CAN;      /* can设备板卡标识 */
    can_create(&cr);          /* CAN初始化使用的函数 */
}

/**
 * @函数名: tCanRecv
 * @参数: RxCan：can设备名数组，代表第X路CAN设备
 * @返回值: 无
 * @函数描述: 提供CAN设备接收例程，CAN接收使用阻塞read方式
 */
void tCanRecv(int RxCan) {
    int ret = 0;
    int fd = 0;
    int id;
    int length = 0;
    int sum = 0;
    int i = 0;
    SjaFrame_t sja_frame;
    SjaPara_t sja_para;

    fd = open(Can_name[RxCan], O_RDWR, 0);
    if (fd == -1) {
        printf("open %s failed!%d\n", Can_name[RxCan], errno);
        return -1;
    }
    /* 采样方式：SINGLE_POINT 或 TRI_POINT */
    sja_para.sample_point = SINGLE_POINT;
    sja_para.can_baudrate = BAUD_500K; /* 测试使用500k波特率 */
    sja_para.can_acr = 0x00000000;     /* 不过滤CAN FRAME */
    sja_para.can_amr = 0xffffffff;
    /* can配置接口 */
    ret = ioctl(fd, IOCTL_INIT_SJA, (int)&sja_para);
    if (ret != 0) {
        printf("CAN %d ioctl(IOCTL_INIT_SJA) failed!%d\n", RxCan, ret);
        ret = -2;
        return ret;
    }

    for (;; sum += length) {
        /* 阻塞读取can帧 */
        length = read(fd, (char *)&sja_frame, sizeof(SjaFrame_t));
        if (length == 0) {
            printf("read return 0!\n");
        }
        if (length == -1) {
            printf("read failed!%d\n", errno);
            ret = -2;
            return ret;
        }
        /*  判断can结构 SFF:标准帧  EFF：扩展帧 */
        if (sja_frame.frame_type == FRAME_EFF) {
            id = sja_frame.frame_id & FRAME_EFF_MASK;
            printf("--- eff id=0x%x data=", id);

            for (i = 0; i < sja_frame.frame_dlc; i++) {
                printf("%02x ", sja_frame.frame_data[i]);
            }

            printf("--- can%d\n", RxCan + 1);
        } else {
            id = sja_frame.frame_id & FRAME_SFF_MASK;
            printf("--- sff id=0x%x data=", id);

            for (i = 0; i < sja_frame.frame_dlc; i++) {
                printf("%02x ", sja_frame.frame_data[i]);
            }

            printf("--- can%d\n", RxCan + 1);
        }
    }
}

/**
 * @函数名: tCanSend
 * @参数: 无
 * @返回值: 0：成功， 其他：失败
 * @函数描述: 提供can发送数据帧例程
 */
int tCanSend(void) {
    int fd = 0;
    int ret = 0;
    int i = 0;
    int input;

    SjaFrame_t sja_frame;
    SjaPara_t sja_para;

    printf("Please input CAN index.(1-2)\n");
    printf("Your choice: %d\n", input = GetKeyInput(10));

    fd = open(Can_name[input - 1], O_RDWR, 0);
    if (fd == -1) {
        ret = -1;
        return ret;
    }
    /* 采样方式：SINGLE_POINT 或 TRI_POINT */
    sja_para.sample_point = SINGLE_POINT;
    sja_para.can_baudrate = BAUD_500K;
    sja_para.can_acr = 0x00000000; /* 不过滤CAN FRAME */
    sja_para.can_amr = 0xffffffff;
    ret = ioctl(fd, IOCTL_INIT_SJA, (int)&sja_para);
    if (ret != 0) {
        printf("CAN %d ioctl(IOCTL_INIT_SJA) failed!%d\n", input - 1, ret);
        ret = -2;
        return ret;
    }

    sja_frame.frame_type = FRAME_SFF; /* 标准帧 FRAME_SFF， 扩展帧 FRAME_EFF*/
    sja_frame.frame_dlc = 8;          /* 8数据字 */

    sja_frame.frame_id = 0x734 & FRAME_SFF_MASK; /* ID */

    /* DATA */
    sja_frame.frame_data[0] = 0x55;
    sja_frame.frame_data[1] = 0x66;
    sja_frame.frame_data[2] = 0x77;
    sja_frame.frame_data[3] = 0x88;
    sja_frame.frame_data[4] = 0x99;
    sja_frame.frame_data[5] = 0xAA;
    sja_frame.frame_data[6] = 0xBB;
    printf("CAN Test, Input Transmit Count(1-10000)\n");
    printf("Your choice: %d\n", input = GetKeyInput(10));

    for (i = 0; i < input; i++) {
        sja_frame.frame_data[7] = i;
        ret = write(fd, (char *)&sja_frame, sizeof(SjaFrame_t));
        if (ret < 0) {
            printf("write failed!%d\n", ret);
        }
        taskDelay(10);
    }

    close(fd);

    return ret;
}

/**
 * @函数名: TestCan
 * @参数: 无
 * @返回值: 无意义
 * @函数描述: 提供测试CAN通用测试程序入口函数
 */
int TestCan(void) {
    int i;
    int input;
    char name[10];

    if (init_can == 0) {
        for (i = 0; i < 2; i++) {
            sprintf(name, "tCanRecv%d", i + 1);
            taskSpawn(name, 100, 0, 1024 * 64, (FUNCPTR)tCanRecv, i, 0, 0, 0, 0,
                      0, 0, 0, 0, 0);
            init_can = 1;
        }
    }

    for (;;) {
        printf(
            "\n"
            "1.CAN Transmit\n"
            "other. Exit\n");
        printf("Your choice: %d\n", input = GetKeyInput(10));

        switch (input) {
            case 1: {
                tCanSend();
                break;
            }
            default: { return 0; }
        }
    }

    return 0;
}

/**
 * @函数名: GetKeyInput
 * @参数: radix：10 ：10进制，16：16进制
 * @返回值: 获取键值数
 * @函数描述: 提供获取键值函数，避开使用sprintf的 bug
 */
static int GetKeyInput(int radix) {
    char input = 0;
    int value = 0;

    if (radix == 10) {
        while ((input = getchar()) != 0x0a) {
            value = value * 10 + (input - 0x30);
        }
    } else {
        while ((input = getchar()) != 0x0a) {
            if (input <= 0x39) {
                input -= 48;
            } else if (input <= 0x46) {
                input -= 55;
            } else {
                input -= 87;
            }
            value = (value << 4) + input; /* ת����ʮ�������� */
        }
    }

    return value;
}