/**
    @file       sjaDrv.h
    @brief      VxWorks下sja1000驱动
    @copyright  senbo
    @author     nick.xu
    @version    V1.0
    @date       2018.04.12 V1.0 创建
    @note       程序用来实现sja1000芯片驱动, 可以配合上层设备驱动使用.
*/

#ifndef SJADRV_H
#define SJADRV_H

#define MAX_SJA_DEVICE      (8)
#define IOCTL_SHOW_DRIVER   (1)
#define IOCTL_INIT_SJA    (2)
#define IOCTL_FLUSH    (3)

typedef struct SjaResource_s
{
    int sja_id;
    int base;
    int fd;
} SjaResource_t;

typedef struct SjaPara_s
{
	int sample_point;
    int can_baudrate;
	unsigned int can_acr;
	unsigned int can_amr;
} SjaPara_t;

#ifdef __cplusplus
extern "C" {
#endif

int sja_drv();
int sja_create(SjaResource_t *pSR);
int sja_remove(char *name);

#ifdef __cplusplus
}
#endif

#endif
