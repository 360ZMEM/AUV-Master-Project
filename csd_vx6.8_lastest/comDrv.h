/**
    @file       comDrv.h
    @brief      VxWorks涓媍om椹卞姩绋嬪簭
    @copyright  senbo
    @author     nick.xu
    @version    V1.0
    @date       2018.04.11 V1.0 鍒涘缓
    @note       绋嬪簭鐢ㄦ潵瀹炵幇com椹卞姩, 鐞嗚鏀寔鍩轰簬i8250鐨勫悇绉嶈姱鐗囨垨閫昏緫.
                鍙敮鎸丳IC妯″紡鍏变韩涓柇.
*/

#ifndef COMDRV_H
#define COMDRV_H

#define MAX_COM_DEVICE      (2)
#define MAX_I8250_DEVICE    (8)
#define IOCTL_SHOW_DRIVER   (1)

#define INT_NUM_IRQ0        0x20                    /* 姝ゅ娉ㄦ剰褰撲笉鏄娇鐢≒IC妯″紡鏃堕渶瑕佷慨鏀� */
#define INT_VEC_GET(irq)    (INT_NUM_IRQ0 + irq)
#define INT_NUM_IRQ0            0x20                    /* 此处注意当不是使用PIC模式时需要修改 */
#define INT_VEC_GET(irq)        (INT_NUM_IRQ0 + irq)
typedef struct ComResource_s
{
    int type;
    int base[4];
	int irq[4];
    int isr_base;
    int nchannel;
    int fifo;
    char description[256];
} ComResource_t;

#ifdef __cplusplus
extern "C" {
#endif

int ComDrv();
int ComCreate(ComResource_t *pDR);
int ComRemove(int fd);
int ComShow(int fd);

#ifdef __cplusplus
}
#endif

#endif
