/*
*
@file		agreedterms.h
@brief	
*/


#ifndef _AGREEDTERMS_H
#define _AGREEDTERMS_H

/**
 * The 8-bit  type.
 */

typedef char int8;
typedef unsigned char byte;
typedef unsigned char u8;
typedef unsigned char uint8;
typedef volatile char vint8;
typedef volatile unsigned char vuint8;
typedef unsigned char uint8_t;

/**
 * The 16-bit  type.
 */
typedef int int16;
typedef unsigned short int u16;
typedef unsigned short uint16;
typedef unsigned short int uint16_t;	

/**
 * The 32-bit  type.
 */
typedef unsigned int u32; 
typedef long int32;
typedef unsigned long uint32;


	
typedef enum {false, true} bool;


/*==========================================================================
 * UDP 日志重定向宏
 * 
 * 将所有 printf 调用重定向到 udp_log_printf(), 通过以太网 UDP 发送到上位机。
 * 接收端: PC/Jetson 运行 scripts/log_receiver.py (监听 UDP 52367)
 *
 * 要恢复原始 printf (串口输出), 注释掉下面的 #define 即可。
 *==========================================================================*/
#include "UdpLogger.h"

/* 宏展开: 将 printf 替换为 udp_log_printf */
#define printf  udp_log_printf


#endif

