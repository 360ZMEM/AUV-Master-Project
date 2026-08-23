#include <vxWorks.h>
#include <sysLib.h>
#include <taskLib.h>
#include <stdio.h>
#include <stdlib.h>
#include <wdLib.h>
#include <string.h>
#include <main.h>

#include <tickLib.h>

/*��̫�������ͷ�ļ�*/
#include <sockLib.h>
#include <inetLib.h>
#include <stdioLib.h>
#include <strLib.h>
#include <hostLib.h>
#include <ioLib.h>
#include <ioctl.h>
#include <fioLib.h>

/*��������ͷ�ļ�*/
#include <selectLib.h>

#include "com.h"
#include "DataProcess.h"
#include "PowerManage.h"
#include "SailingBox.h"
#include "SecurityEmergencyManage.h"
#include "dtp.h"




/*������̫���豸IP��ַ*/
#define LocalIP  "192.168.0.101"
#define UIControllerIP "192.168.0.11"
#define FMCUIP "192.168.0.30"/*��һ΢������*/

/*������̫���豸�˿ں�*/
#define LocalPort 5000
#define FMCUPort 8089
#define UIControllerPort 21

unsigned char CCTXA(unsigned char BW_Data[],uint8_t Len_BW);
void UartSendToBEIDOUTask(void);
void UartRecvFormBEIDOUTask(void);

void NetSendTask(void);
void NetRecvTask(void);

void UartSendToPSDTask(void);
void UartRecvFormPSDTask(void);


void UartRecvFormGPSTask(void);
void UartRecvFormDVLTask(void);


void UartRecvFormIMUTask(void);

void UartSendToLORATask(void);
void UartRecvFormLORATask(void);


void UartRecvFormBMSTask(void);

STATUS UdpSocketInit (const char * deviceIP, const u16 devicePort);

/*�������ݸ������豸����*/
int Send_To_BEIDOU(void);
int Send_To_FMCU(void);
int Send_To_PSD(void);
int Send_To_LORA(void);
int Send_To_WIFI(void);

/*�������ݸ������豸����*/
bool Recv_From_BEIDOU(u8 *temp, int length);
bool Recv_From_PSD(u8 *temp, int length);
bool Recv_From_GPS_GGA(u8 *temp, int length);
bool Recv_From_GPS_VTG(u8 *temp, int length);
bool Recv_From_DVL_BI(u8 *temp, int length);
bool Recv_From_DVL_BD(u8 *temp, int length);
bool Recv_From_DVL_WI(u8 *temp, int length);
bool Recv_From_DVL_WD(u8 *temp, int length);
bool Recv_From_DVL_ACK(u8 *temp, int length);
bool Recv_From_IMU(u8 *temp, int length);
bool Recv_From_WIFI(void);
bool Recv_From_LORA(u8 *temp, int length);
bool Recv_From_BMS_SS(u8 *temp, int length);
bool Recv_From_BMS_CS(u8 *temp, int length);
bool Recv_From_FMCU(void);

void Perror(const char *s);
bool Lan_Recv_Data_Validity_check(u8 *check_head_buf, u8 *check_end_buf, u8 *receive_data, u16 received_len);

#define BEID_COM_BAUD_RATE           115200  /* �������ڲ����� */
#define GPS_COM_BAUD_RATE           9600  /* GPS���ڲ����� */
#define PSD_COM_BAUD_RATE           9600  /* Ƶ���ƴ��ڲ����� */
#define DVL_COM_BAUD_RATE           38400  /* DVL���ڲ����� ,ע�����ﲨ����Ҫ�ĳ�38400����Ӧdvl�豸*/
#define IMU_COM_BAUD_RATE           115200  /* �����Ǵ��ڲ����� */
#define LORA_COM_BAUD_RATE           38400  /* LORA���ڲ����� */
#define BMS_COM_BAUD_RATE           115200  /* LORA���ڲ����� */


/*��־����*/
bool Recv_From_WIFI_Correct_Flag = false;
bool WIFI_Socket_Initial_Flag = false;

bool Recv_From_WIFI_OK_No_Flag = false;

bool Recv_From_FMCU_Correct_Flag = false;
bool FMCU_Socket_Initial_Flag = false;


bool Recv_From_LORA_Correct_Flag = false;
bool Recv_From_BEIDOU_Correct_Flag = false;

bool Recv_From_GPS_GGA_Correct_Flag = false;
bool Recv_From_GPS_VTG_Correct_Flag = false;
bool Recv_From_GPS_QC_Flag = false;

bool BI_Data_Valid_Flag = false;
bool BD_Data_Valid_Flag = false;
bool WI_Data_Valid_Flag = false;
bool WD_Data_Valid_Flag = false;
bool ACK_Data_Valid_Flag = false;

bool BI_Cal_Data_Flag = false;
bool WI_Cal_Data_Flag = false;

bool Recv_From_IMU_Correct_Flag = false;

bool Recv_From_BMS_SS_Correct_Flag = false;
bool Recv_From_BMS_CS_Correct_Flag = false;

bool Recv_From_PSD_Correct_Flag = false;



u16 ToUI12_Msg_Length = 145;/*�������µ�Э�飬cpu����λ������������144���ֽڣ����Ͻ�������145*/
u16 From_UI_WIFI_Length = 72;/*�������µ�Э�飬��λ��������������71���ֽڣ����Ͻ�������72*/

u16 ToLORALength = 145;/*�������µ�Э�飬������144���ֽڣ����Ͻ�������145*/
u16 FromLORALength = 72;/*�������µ�Э�飬������71���ֽڣ����Ͻ�������72*/

u16 ToUI3_Msg_Length = 72;/*�ݶ�����Ҫ�޸�*/
u16 From_UI_BEIDOU_Length = 34;

u16 From_DVL_BI_Length = 240;
u16 From_DVL_BD_Length = 240;
u16 From_DVL_WI_Length = 240;
u16 From_DVL_WD_Length = 240;



u16 From_BMS_SS_Length = 28;
u16 From_BMS_CS_Length = 8;

u16 FromMCULength = 86;/*�������µ�Э�飬������  ���ֽڣ����Ͻ�������  ԭ����45*/

u16 FromPSDLength = 4;/*�������µ�Э�飬������  ���ֽڣ����Ͻ�������  */


u16 From_IMU_Length =32;

u8 To_UI12_Buf[145] = {0};
u8 From_WIFI_Buf[72] = {0};

u8 to_LORA_buf[145] = {0};
u8 From_LORA_Buf[72] = {0};

/*bms���β�ѯ���� �ֿ��������ո���"������"��"�ֽ���"���������ж���summary_state����critical_state������֡*/
u8 to_BMS_summary_state_buf[8] = {0x01,0x03,0x21,0x00,0x00,0x0D,0x8E,0x33};
u8 to_BMS_critical_state_buf[8] = {0x01,0x03,0x21,0x40,0x00,0x02,0xCF,0xE3};
u8 From_BMS_SS_Buf[240] = {0};
u8 From_BMS_CS_Buf[240] = {0};

u8 From_GPS_GGA_Buf[240] = {0};
u8 From_GPS_VTG_Buf[240] = {0};

u8 From_DVL_BI_Buf[240] = {0};
u8 From_DVL_BD_Buf[240] = {0};
u8 From_DVL_WI_Buf[240] = {0};
u8 From_DVL_WD_Buf[240] = {0};
u8 From_DVL_ACK_Buf[240] = {0};

u8 to_Compass_buf[1] = {0xCF};
u8 From_IMU_Buf[32] = {0};


u8 To_UI3_Buf[256] = {0};
u8 CCTXA_Buf[256] = {0};



u8 to_MCU_buf[200]={0};/*�������µ�Э�飬������    ���ֽڣ����Ͻ�������  */
u8 From_FMCU_Buf[200] = {0};/*�������µ�Э�飬������39���ֽڣ����Ͻ�������40*/




u8 From_BEIDOU_Buf[256] = {0};
u8 From_BEIDOU_Buf_Self[256] = {0};




u8 to_PSD_buf[5] = {0};
u8 From_PSD_Buf[5] = {0};

u8 GPS_Recv_num=0;


/*������̫���豸UDP���������׽���*/

short int MCUFd = 0;
short int UIControllerFd = 0;
short int UdpSockFd = 0;





void UartSendToLORATask(void)
{
	        FOREVER
			{
				if(semTake(semUartSendToLORATask,WAIT_FOREVER)==OK)/*�����ݷ��͸������豸�����С��1mʱ�ͷ��ź���*/
				{
					printf("UartSendToLORATask start::::\r\n");
					Pack_Data_To_UI12(&To_UI12);
					Send_To_LORA();
				
									
				}
			}	
}




int Send_To_LORA(void)
{
	    int fd = 0;
		int TxCom = 18;
		int usart_sent_to_LORA = 0;
		int ret = 0;
					
		/* �򿪷��ʹ���1 */
		fd = open(g_ExtComName[TxCom], O_RDWR, 0);
		if (fd == ERROR)
		{
			printf("Open %s failed!\n", g_ExtComName[TxCom]);
			return fd;
		}
		/* ���ô��ڲ��� */
		/* ����λ8λ ֹͣλ1λ ��У�� ����ģʽ  */
		ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8 );
		ret += ioctl(fd, FIOBAUDRATE, LORA_COM_BAUD_RATE);   /* ������ */
		ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
		ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */
		usart_sent_to_LORA = write(fd, (char *)To_UI12_Buf, 145);
		/* VxWorks���ڷ��ͺ����޷��������Է��������Ҫ�����ȴ���� ��ʱʹ����ʱʵ�� */
		taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
		memset(to_LORA_buf, 0, 145);/**/
		/*printf("COM:%d usart_sent_to_LORA:%d\n", TxCom + 1, usart_sent_to_Compass);*/
		/* ���뱣֤���ݷ�����ɺ� ���ܹرմ��� */
		close(fd);
		taskDelay(sysClkRateGet() / 10);
		return usart_sent_to_LORA;
}





void UartSendToPSDTask(void)
{
	FOREVER
		{
			if(semTake(semUartSendToPSDTask,WAIT_FOREVER)==OK)/*�����ݷ��͸������豸�����С��1mʱ�ͷ��ź���*/
			{
				printf("UartSendToPSDTask start::::\r\n");
				Pack_Data_To_PSD(&AnswerDataToPSD);
				Send_To_PSD();
			
			}
		}	
}


int Send_To_PSD(void)
{
	int fd = 0;
	int TxCom = 3;
	int usart_sent_to_PSD = 0;
	int ret = 0;
				
	/* �򿪷��ʹ���1 */
	fd = open(g_ExtComName[TxCom], O_RDWR, 0);
	if (fd == ERROR)
	{
		printf("Open %s failed!\n", g_ExtComName[TxCom]);
		return fd;
	}
	/* ���ô��ڲ��� */
	/* ����λ8λ ֹͣλ1λ ��У�� ����ģʽ */
	ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8);
	ret += ioctl(fd, FIOBAUDRATE, PSD_COM_BAUD_RATE);   /* ������ */
	ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
	ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */
	usart_sent_to_PSD = write(fd, (char *)to_PSD_buf, 5);
	/* VxWorks���ڷ��ͺ����޷��������Է��������Ҫ�����ȴ���� ��ʱʹ����ʱʵ�� */
	taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
	memset(to_PSD_buf, 0, 5);
	/*printf("COM:%d usart_sent_to_PSD:%d\n", TxCom + 1, usart_sent_to_PSD);*/
	/* ���뱣֤���ݷ�����ɺ� ���ܹرմ��� */
	close(fd);
	taskDelay(sysClkRateGet() / 10);
	return usart_sent_to_PSD;	
}


/*
 BW_Data[] ��Ҫ���͵ı�������
 Len_BW ���ĳ���*/

unsigned char CCTXA(unsigned char BW_Data[],uint8_t Len_BW) 
{
unsigned char return_data=0;
uint8_t $CCTXA[256];
uint8_t i,j=0;
uint32_t RD21_dest_ICnum; 
uint8_t RD21_Temp_H,RD21_Temp_L;
uint8_t RD21_Temp_CRC[256];
uint8_t RD21_Temp_CRC_H,RD21_Temp_CRC_L;
/*RD21_dest_ICnum= Dest_ICnum [0]*256*256+ Dest_ICnum [1]*256+ Dest_ICnum [2];*/
RD21_dest_ICnum=989564;
$CCTXA[0]='$';
$CCTXA[1]='C';
$CCTXA[2]='C';
$CCTXA[3]='T';
$CCTXA[4]='X';
$CCTXA[5]='A';
$CCTXA[6]=',';
$CCTXA[7]=(RD21_dest_ICnum/1000000)+'0';
$CCTXA[8]=(RD21_dest_ICnum%1000000)/100000+'0';
$CCTXA[9]=((RD21_dest_ICnum%1000000)%100000)/10000+'0';
$CCTXA[10]=(((RD21_dest_ICnum%1000000)%100000)%10000)/1000+'0';
$CCTXA[11]=((((RD21_dest_ICnum%1000000)%100000)%10000)%1000)/100+'0';
$CCTXA[12]=(((((RD21_dest_ICnum%1000000)%100000)%10000)%1000)%100)/10+'0';
$CCTXA[13]=(((((RD21_dest_ICnum%1000000)%100000)%10000)%1000)%100)%10+'0';
$CCTXA[14]=',';
$CCTXA[15]='1';
$CCTXA[16]=',';
$CCTXA[17]='2';
$CCTXA[18]=',';
$CCTXA[19]='A';
$CCTXA[20]='4';
for(i=0;i<Len_BW;i++)
{
RD21_Temp_H=BW_Data[i]>>4;
$CCTXA[21+j*2]=HEX_to_ASCII(RD21_Temp_H);
RD21_Temp_L=BW_Data[i]<<4;
RD21_Temp_L=RD21_Temp_L>>4;
$CCTXA[22+j*2]=HEX_to_ASCII(RD21_Temp_L);
j++;
}
j=0;
for(i=0;i<20+Len_BW*2;i++) RD21_Temp_CRC[i]=$CCTXA[i+1];
RD21_Temp_CRC[20+Len_BW*2]=Data_XOR(RD21_Temp_CRC,20+Len_BW*2);
RD21_Temp_CRC_H=RD21_Temp_CRC[20+Len_BW*2]>>4;
RD21_Temp_CRC_L=RD21_Temp_CRC[20+Len_BW*2]<<4;
RD21_Temp_CRC_L=RD21_Temp_CRC_L>>4;
$CCTXA[20+Len_BW*2+1]='*';
$CCTXA[20+Len_BW*2+2]=HEX_to_ASCII(RD21_Temp_CRC_H);
$CCTXA[20+Len_BW*2+3]=HEX_to_ASCII(RD21_Temp_CRC_L);
$CCTXA[20+Len_BW*2+4]=0x0D;
$CCTXA[20+Len_BW*2+5]=0x0A;


memcpy(CCTXA_Buf,$CCTXA,20+Len_BW*2+5);

return return_data;
}



void UartSendToBEIDOUTask(void)
{
	FOREVER
	{
		if(semTake(semUartSendToBEIDOUTask,WAIT_FOREVER)==OK)/*�����ݷ��͸������豸�����С��1mʱ�ͷ��ź���*/
		{
			printf("UartSendToBEIDOUTask start::::\r\n");		
	
			
			Pack_Data_To_UI3(&ToUI3);
			CCTXA(To_UI3_Buf,72);
			Send_To_BEIDOU();
			
		
		}
	}	
}

void NetSendTask(void)
{
	
	FOREVER
	{
		if(semTake(semNetSendTask,WAIT_FOREVER)==OK)/*�����ݷ��͸������豸��*/
		{
			printf("NetSendTask start::::\r\n");
			
			
			if(1)
			{
				if(false == WIFI_Socket_Initial_Flag)
				{
					UdpSocketInit(UIControllerIP, UIControllerPort);
				}
				else
				{	
					Pack_Data_To_UI12(&To_UI12);
					Send_To_WIFI();					
				}
			}
			
			if(1)
			{
				if(false == FMCU_Socket_Initial_Flag)
				{
				    UdpSocketInit(FMCUIP, FMCUPort);
				}
			    else
				{			    	
			    	Send_To_FMCU();
			    }
			}
			
			
			
			
		}
	}
}

void NetRecvTask(void)
{
	FOREVER
	{
		if(OK == semTake(semNetRecvTask,WAIT_FOREVER))
		{
	      printf("semNetRecvTask start::::\r\n");
		  if(1)/*ԭ�����ж������ǣ�((Instruction_To_FMCU.McuFD_Power_Control)&0x40)==0x40*/
		  {
			if(Recv_From_WIFI_Correct_Flag == false)
			{
				if(false == WIFI_Socket_Initial_Flag)
				{
					UdpSocketInit(UIControllerIP, UIControllerPort);
				}
				else
				{					
					Recv_From_WIFI_Correct_Flag = Recv_From_WIFI();
					
					if(Recv_From_WIFI_Correct_Flag == false)
					{
						Not_Recv_From_WIFI_No++;
					}
					else
					{
						;
					}
				}
			}
		  }
		  else
		  {
			  Not_Recv_From_WIFI_No = 0;
		  }
		  
		  
			if(Recv_From_FMCU_Correct_Flag == false)
			{
				if(false == FMCU_Socket_Initial_Flag)
				{
					UdpSocketInit(FMCUIP, FMCUPort);
				}
				else
				{						
					Recv_From_FMCU_Correct_Flag = Recv_From_FMCU();
				}
			}	
			
		    if((Recv_From_WIFI_Correct_Flag == true)||(Recv_From_FMCU_Correct_Flag == true))		
		    {
			   semGive(semUnpackNetDataTask);
		    }
			
		}
	}
}

int Send_To_FMCU(void)
{
	struct sockaddr_in serverAddr;   /*�������˵�ַ�ṹ��*/
	int sent_to_MCU = 0;
	
	
	/* �������� */
	memset(&serverAddr, 0x00, sizeof(struct sockaddr_in));
	serverAddr.sin_family = AF_INET;
	serverAddr.sin_addr.s_addr = inet_addr(FMCUIP);
	serverAddr.sin_port = htons(FMCUPort);
	
	
	 /* �������� */
	sent_to_MCU = sendto(MCUFd, (char *)to_MCU_buf, sizeof(to_MCU_buf), 0, (struct sockaddr *)&serverAddr, sizeof(struct sockaddr_in));
	memset(to_MCU_buf, 0, 60);/*30��to_MCU_buf����ĳ��ȣ����Ͻ�������*/
	
	taskDelay(sysClkRateGet() *0.03);    /* VxWorks sendto������bug �޷����������ݷ������,��ʱ30ms */
	/*printf("sent_to_UIController = %d\n", sent_to_UIController);
	printf("Packets are sent to %s:%d.\n", UIControllerIP, UIControllerPort);*/
	
	return sent_to_MCU;
}



int Send_To_WIFI(void)
{
	struct sockaddr_in serverAddr;   /*�������˵�ַ�ṹ��*/
	int sent_to_UIController = 0;
	
	
	/* �������� */
	memset(&serverAddr, 0x00, sizeof(struct sockaddr_in));
	serverAddr.sin_family = AF_INET;
	serverAddr.sin_addr.s_addr = inet_addr(UIControllerIP);
	serverAddr.sin_port = htons(UIControllerPort);
	
	
	 /* �������� */
	sent_to_UIController = sendto(UIControllerFd, (char *)To_UI12_Buf, sizeof(To_UI12_Buf), 0, (struct sockaddr *)&serverAddr, sizeof(struct sockaddr_in));
	memset(To_UI12_Buf, 0, ToUI12_Msg_Length);
	
	taskDelay(sysClkRateGet() *0.03);    /* VxWorks sendto������bug �޷����������ݷ������,��ʱ30ms */
	/*printf("sent_to_UIController = %d\n", sent_to_UIController);
	printf("Packets are sent to %s:%d.\n", UIControllerIP, UIControllerPort);*/
	
	return sent_to_UIController;
}


bool Recv_From_FMCU(void)
{
	
	u16 ii = 0, jj = 0;
	struct sockaddr_in serverAddr;   /*�������˵�ַ�ṹ��*/
	int socketLength = sizeof(struct sockaddr_in);
	int length = 0;
	u8 temp_buf[1024] = {0};
	bool check_flag = false;
	
	/* �������� */
	memset(&serverAddr, 0x00, sizeof(struct sockaddr_in));
	serverAddr.sin_family = AF_INET;
	serverAddr.sin_addr.s_addr = inet_addr(FMCUIP);
	serverAddr.sin_port = htons (FMCUPort);
	
	/*printf("Wait for a response from MCU.\n");*/
	length = recvfrom(MCUFd, (char *)temp_buf, 1024, 0, (struct sockaddr *)&serverAddr, &socketLength);
	/*printf("length=%d",length);*/
	for(ii = 0; ii < length; ii++)
	{
		/**************************************************** ң   ��  ģ    ʽ   *****************************************************/
		/*printf("length:%d",length);*/
		if((ii + FromMCULength - 1) < length)
		{
			/*֡ͷ֡β�ж�*/
			/*printf("1:%c%c%c%c%c%c",temp_buf[0],temp_buf[1],temp_buf[2],temp_buf[3],temp_buf[4],temp_buf[5]);*/
			   if((temp_buf[ii] == '$') && (temp_buf[ii + 1] == 'M') && 
			   (temp_buf[ii + 2] == 'C') && (temp_buf[ii + 3] == 'U') && (temp_buf[ii + 4] == 'F') && (temp_buf[ii + 5] == 'U') 
			   )			
		       {		
				   
					for(jj = 0; jj < FromMCULength; jj++)
					{
						From_FMCU_Buf[jj] = temp_buf[jj + ii];						
					}				
					check_flag = true;           /*У��ͨ��*/
					break;
			   }
			   else
			   {
				   check_flag = false;
				   continue;
			   }
		    }
		    else
		    {			
			      check_flag = false;
			      break;
		    }
	}
	/* ��ӡ���յ����� */
	if(DEBUG)
	{
		
		/*printf("From_FMCU_Buf raw data length:%d\n", length);*/
	    
	}	
	return check_flag;
}




bool Recv_From_WIFI(void)
{
	u8 bytesum = 0;
	u16 ii = 0, jj = 0;
	int length = 0;
	struct sockaddr_in serverAddr;   /*�������˵�ַ�ṹ��*/
	int socketLength = sizeof(struct sockaddr_in);

	u8 temp_buf[1024] = {0};
	bool check_flag = false;
	
	/* �������� */
	memset(&serverAddr, 0x00, sizeof(struct sockaddr_in));
	serverAddr.sin_family = AF_INET;
	serverAddr.sin_addr.s_addr = inet_addr(UIControllerIP);
	serverAddr.sin_port = htons (UIControllerPort);
	
	/*printf("Wait for a response from UIWifi.\n");*/
	length = recvfrom(UIControllerFd, (char *)temp_buf, 1024, 0, (struct sockaddr *)&serverAddr, &socketLength);
	/*printf("length=%d",length);*/
	
	for(ii = 0; ii < length; ii++)
	{
		/**************************************************** ң   ��  ģ    ʽ   *****************************************************/
		if((ii + From_UI_WIFI_Length - 1) < length)
		{
			 
			/*֡ͷ֡β�ж�*/
			if((temp_buf[ii] == 0x24) && (temp_buf[ii + 1] == 0x43) && 
			   (temp_buf[ii + 2] == 0x4b) && (temp_buf[ii + 3] == 0x54) && (temp_buf[ii + 4] == 0x48) &&      
			   (temp_buf[ii + 70] == 0xFF) && (temp_buf[ii + 71] == 0xFF))
			   {	
				   
					for(jj = 0; jj < From_UI_WIFI_Length; jj++)
					{
						From_WIFI_Buf[jj] = temp_buf[jj + ii];
					}
					
					bytesum = Check_Sum(From_WIFI_Buf, From_UI_WIFI_Length - 3);
					
					/*У����жϣ��ۼӺ�*/
					if(bytesum != (From_WIFI_Buf[69]))
					{
						printf("data_from_UIWifi check sum is wrong!::\n");
						printf("bytesum:%4x From_WIFI_Buf[69]:%2x%\n", bytesum, From_WIFI_Buf[69]);
						/*printf("crc16:%4x From_WIFI_Buf[22-23]:%2x%2x\n", crc16, From_WIFI_Buf[22], From_WIFI_Buf[23]);*/
						memset(From_WIFI_Buf, 0, From_UI_WIFI_Length);
						check_flag = false;
						return check_flag;
					}
					check_flag = true;           /*У��ͨ��*/
					UI_Channel_Selection_Down = 0x02;/*����wifiͨ����־λ��*/				
					PC104_Timing_Record_WIFI_Downlink(From_WIFI_Buf[5]);
					break;
			   }
			   else
			   {
				   check_flag = false;
				   continue;
			   }
		}
		else
		{			
			check_flag = false;
			break;
		}
	}
	

	
	/* ��ӡ���յ����� */
	if(DEBUG)
	{
		
		/*printf("From_WIFI_Buf raw data length:%d\n", length);*/
	    
	}	
	return check_flag;
}




int Send_To_BEIDOU(void)
{
	    int fd = 0;
		int TxCom = 1;
		int usart_sent_to_beid = 0;
		int ret = 0;
				
		 /* �򿪷��ʹ���1 */
		fd = open(g_ExtComName[TxCom], O_RDWR, 0);
		if (fd == ERROR)
		{
			printf("Open %s failed!\n", g_ExtComName[TxCom]);
			return fd;
		}
		/*printf("fd=%d", fd);*/
		/* ���ô��ڲ��� */
			/* ����λ8λ ֹͣλ1λ ��У�� ����ģʽ   */
		ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8);
		ret += ioctl(fd, FIOBAUDRATE, BEID_COM_BAUD_RATE);   /* ������ */
		ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
		ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */
		usart_sent_to_beid = write(fd, (char *)CCTXA_Buf, 256);
		/* VxWorks���ڷ��ͺ����޷��������Է��������Ҫ�����ȴ���� ��ʱʹ����ʱʵ�� */
		taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
		memset(To_UI3_Buf, 0, 97);
		/*printf("COM:%d usart_sent_to_beid:%d\n", TxCom + 1, usart_sent_to_beid);*/
		/* ���뱣֤���ݷ�����ɺ� ���ܹرմ��� */
		close(fd);
		taskDelay(sysClkRateGet() / 10);
		return usart_sent_to_beid;
	
}



void UartRecvFormBMSTask(void)
{
	 FOREVER
			{			
				if(semTake(semUartRecvFormBMSTask,WAIT_FOREVER)==OK)
				{
					
					printf("UartRecvFormBMSTask start::::\r\n");
					int fd = 0;
					int RxCom = 16;
					int ret = 0;
					int ii;
					u8 temp_buf_SS[1024] = {0};
					u8 temp_buf_CS[1024] = {0};
					int msg_length_SS = 0;
					int msg_length_CS = 0;
					struct timeval timeout;							
								
					/* �򿪽��մ��� */
					fd = open(g_ExtComName[RxCom], O_RDWR, 0);
					if (fd == ERROR)
					{
						printf("Open %s COM failed!\n", g_ExtComName[RxCom]);
						return;
					}
					
					/* ���ô��ڲ��� */
					/* ����λ8λ ֹͣλ1λ ��У�� ����ģʽ*/
					ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8 );
					ret += ioctl(fd, FIOBAUDRATE, BMS_COM_BAUD_RATE);   /* ������ */
					ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
				    ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */
					
				    write(fd, (char *)to_BMS_critical_state_buf, 8);	/*ɾ��*/
				    
					/* ��ӡ�������� */
					/* ��ʱ��ȡģʽ */
					/* ���ó�ʱʱ�� */
					timeout.tv_sec = 0;         /* 0 ��λs */
					timeout.tv_usec = 130000;   /* 130ms ��λus*/
					/*******************************************************************/	
					while(!msg_length_SS)
					{
						write(fd, (char *)to_BMS_summary_state_buf, 8);				
						msg_length_SS = com_read_ex(fd, (char *)temp_buf_SS, sizeof(temp_buf_SS), &timeout);
					}
					 /*��ֵ*/
					if(msg_length_SS)
					{
						for(ii=0;ii<msg_length_SS;ii++)
							From_BMS_SS_Buf[ii]=temp_buf_SS[ii];	
					}	
					/*֡ͷ�ж�*/
					Recv_From_BMS_SS_Correct_Flag= Recv_From_BMS_SS(temp_buf_SS, msg_length_SS);	
					
					/*******************************************************************/	
					
					
					while(!msg_length_CS)
					{
						
						write(fd, (char *)to_BMS_critical_state_buf, 8);						
						msg_length_CS = com_read_ex(fd, (char *)temp_buf_CS, sizeof(temp_buf_CS), &timeout);
					}
					 /*��ֵ*/
					if(msg_length_CS)
					{
						for(ii=0;ii<msg_length_CS;ii++)
					        From_BMS_CS_Buf[ii]=temp_buf_CS[ii];	
					}	
					/*֡ͷ�ж�*/
					Recv_From_BMS_CS_Correct_Flag= Recv_From_BMS_CS(temp_buf_CS, msg_length_CS);	
									
					taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
					close(fd);
					if(((Recv_From_BMS_SS_Correct_Flag)==true)||((Recv_From_BMS_CS_Correct_Flag)==true))
				    {
						semGive(semUnpackBMSDataTask);						
				    }
				}
			}	
	
}


void UartRecvFormLORATask(void)
{
	 FOREVER
			{			
				if(semTake(semUartRecvFormLORATask,WAIT_FOREVER)==OK)
				{
					printf("xxjfdfdsgnfdaiuhruifebryuvbreyuvgbiafhduifabdfidbf");
					printf("UartRecvFormLORATask start::::\r\n");
					int fd = 0;
					int RxCom = 18;
					int ret = 0;
					int ii;
					u8 temp_buf[1024] = {0};
					int msg_length = 0;
					struct timeval timeout;							
								
					/* �򿪽��մ��� */
					fd = open(g_ExtComName[RxCom], O_RDWR, 0);
					if (fd == ERROR)
					{
						printf("Open %s COM failed!\n", g_ExtComName[RxCom]);
						return;
					}
				
					/* ���ô��ڲ��� */
					/*  CS8|PARENB :8λ����λ��1λֹͣλ��żУ�飻
					    CS8|PARENB|PARODD:8λ����λ��1λֹͣλ����У�飻
					    CS8 :8λ����λ��1λֹͣλ����У�飻
					    CS8|STOPB:8λ����λ��2λֹͣλ����У�飻*/
					ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8 );
					ret += ioctl(fd, FIOBAUDRATE, LORA_COM_BAUD_RATE);   /* ������ */
					ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
				    ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */
					
					/* ��ӡ�������� */
					/* ��ʱ��ȡģʽ */
					/* ���ó�ʱʱ�� */
					timeout.tv_sec = 0;         /* 0 ��λs */
					timeout.tv_usec = 130000;   /* 130ms ��λus*/
					while(!msg_length)
					{
						msg_length = com_read_ex(fd, (char *)temp_buf, sizeof(temp_buf), &timeout);
					}
		
					 /*ֱ���յ�ʲô�͸�ֵʲô*/
					if(msg_length)
					{
						for(ii=0;ii<msg_length;ii++)
							From_LORA_Buf[ii]=temp_buf[ii];	
					}
				
					/*printf("Recv_From_LORA[0]:%2x,Recv_From_LORA[1]:%2x",Recv_From_LORA[0],Recv_From_LORA[1]);*/
					/*֡ͷ�ж�*/
					Recv_From_LORA_Correct_Flag= Recv_From_LORA(temp_buf, msg_length);	
					taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
					close(fd);
					if((Recv_From_LORA_Correct_Flag)==true)
					{
						semGive(semUnpackLORADataTask);						
					}
					
				}
			}	
}




void UartRecvFormIMUTask(void)
{
	    FOREVER
		{			
			if(semTake(semUartRecvFormIMUTask,WAIT_FOREVER)==OK)
			{
				printf("UartRecvFormIMUTask start::::\r\n");
				int fd = 0;
				int RxCom = 0;
				int ret = 0;
				int ii;
				u8 temp_buf[1024] = {0};
				int msg_length = 0;
				struct timeval timeout;							
							
				/* �򿪽��մ��� */
				fd = open(g_ExtComName[RxCom], O_RDWR, 0);
				if (fd == ERROR)
				{
					printf("Open %s COM failed!\n", g_ExtComName[RxCom]);
					return;
				}
			
				/* ���ô��ڲ��� */
				/* ����λ8λ ֹͣλ1λ ��У�� ����ģʽ PARODD | PARENB |*/
				ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8 );
				ret += ioctl(fd, FIOBAUDRATE, IMU_COM_BAUD_RATE);   /* ������ */
				ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
			    ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */
				
				/* ��ӡ�������� */
				/* ��ʱ��ȡģʽ */
				/* ���ó�ʱʱ�� */
				timeout.tv_sec = 0;         /* 0 ��λs */
				timeout.tv_usec = 130000;   /* 130ms ��λus*/
				while(!msg_length)
				{
					write(fd, (char *)to_Compass_buf, 1);
					msg_length = com_read_ex(fd, (char *)temp_buf, sizeof(temp_buf), &timeout);
				}
				
				 /*ֱ���յ�ʲô�͸�ֵʲô*/
				if(msg_length)
				{
					for(ii=0;ii<msg_length;ii++)
					From_IMU_Buf[ii]=temp_buf[ii];
				}
				/*��������֡ͷ�ж�*/
				Recv_From_IMU_Correct_Flag= Recv_From_IMU(temp_buf, msg_length);	
				taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
				close(fd);
			    if((Recv_From_IMU_Correct_Flag)==true)
			    { 
			    	semGive(semUnpackIMUDataTask);
			    }
			}
		}	
}







void UartRecvFormPSDTask(void)
{
	FOREVER
		{			
			if(semTake(semUartRecvFormPSDTask,WAIT_FOREVER)==OK)
			{
				printf("UartRecvFromPSDTask start::::\r\n");
				int fd = 0;
				int RxCom = 3;
				int ret = 0;
				int ii;
				u8 temp_buf[1024] = {0};
				int msg_length = 0;
				struct timeval timeout;							
							
				/* �򿪽��մ��� */
				fd = open(g_ExtComName[RxCom], O_RDWR, 0);
				if (fd == ERROR)
				{
					printf("Open %s COM failed!\n", g_ExtComName[RxCom]);
					return;
				}
				/* ���ô��ڲ��� */
				/* ����λ8λ ֹͣλ1λ ��У�� ����ģʽ*/
				ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8);
				ret += ioctl(fd, FIOBAUDRATE, PSD_COM_BAUD_RATE);   /* ������ */
				ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
			    ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */
							
				/* ��ӡ�������� */
				/* ��ʱ��ȡģʽ */
				/* ���ó�ʱʱ�� */
				timeout.tv_sec = 0;         /* 0 ��λs */
				timeout.tv_usec = 130000;   /* 30ms ��λus*/
				while(!msg_length)
				{
					semGive(semUartSendToPSDTask);/*�ͷŷ����ź��������Ƿ����˲�ѯָ��*/				
					msg_length = com_read_ex(fd, (char *)temp_buf, sizeof(temp_buf), &timeout);
				}
				
				 /*ֱ���յ�ʲô�͸�ֵʲô*/
				if(msg_length)
				{
					for(ii=0;ii<msg_length;ii++)
						From_PSD_Buf[ii]=temp_buf[ii];
				}
				/*��������֡ͷ�ж�*/
				Recv_From_PSD_Correct_Flag= Recv_From_PSD(temp_buf, msg_length);	
				taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
				close(fd);
				if((Recv_From_PSD_Correct_Flag)==true)
				{ 
				    semGive(semUnpackPSDDataTask);
				}
			}
		}	
}

void UartRecvFormDVLTask(void)
{
	FOREVER
			{			
				if(semTake(semUartRecvFormDVLTask,WAIT_FOREVER)==OK)
				{
					printf("UartRecvFormDVLTask start::::\r\n");
					printf("xxjhaishiyanhahahhahhah");
					int fd = 0;
					int RxCom = 17;
					int ret = 0;					
					u8 temp_buf[1024] = {0};
					int msg_length = 0;
					struct timeval timeout;							
					char *ptr1 = "";
					char *ptr2 = "";
					char *ptr3 = "";
					char *ptr4 = "";
					char *ptr5 = "";
				
					/* �򿪽��մ��� */
					fd = open(g_ExtComName[RxCom], O_RDWR, 0);
					if (fd == ERROR)
					{
						printf("Open %s COM failed!\n", g_ExtComName[RxCom]);
						return;
					}
					/* ���ô��ڲ��� */
					/* ����λ8λ ֹͣλ1λ ��У�� ����ģʽ*/
					ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8 );
					ret += ioctl(fd, FIOBAUDRATE, DVL_COM_BAUD_RATE);   /* ������ */
					ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
				    ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */
								
					/* ��ӡ�������� */
					/* ��ʱ��ȡģʽ */
					/* ���ó�ʱʱ�� */
					timeout.tv_sec = 0;         /* 0 ��λs */
					timeout.tv_usec = 130000;   /* 30ms ��λus*/
					while(!msg_length)
					{
						msg_length = com_read_ex(fd, (char *)temp_buf, sizeof(temp_buf), &timeout);
					}
					
					
					ptr1 = strstr((char *)temp_buf, ":BI");
					ptr2 = strstr((char *)temp_buf, ":BD");
					ptr3 = strstr((char *)temp_buf, ":WI");	
					ptr4 = strstr((char *)temp_buf, ":WD");
					ptr5 = strstr((char *)temp_buf, ":ACK");
					
					if(ptr1 != NULL)
						BI_Data_Valid_Flag = Recv_From_DVL_BI(temp_buf, msg_length);
								
					if(ptr2 != NULL)
						BD_Data_Valid_Flag = Recv_From_DVL_BD(temp_buf, msg_length);
						
					if(ptr3 != NULL)
						WI_Data_Valid_Flag = Recv_From_DVL_WI(temp_buf, msg_length);
					
					if(ptr4 != NULL)
						WD_Data_Valid_Flag = Recv_From_DVL_WD(temp_buf, msg_length);
					
					if(ptr5 != NULL)
						ACK_Data_Valid_Flag = Recv_From_DVL_ACK(temp_buf, msg_length);
					
					taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
					close(fd);
					
					if(((BI_Data_Valid_Flag)==true)||((BD_Data_Valid_Flag)==true)||
							((WI_Data_Valid_Flag)==true)||((WD_Data_Valid_Flag)==true))
					{
						semGive(semUnpackDVLDataTask);
					}
				}
			}	
	
}




void UartRecvFormGPSTask(void)
{
	FOREVER
		{			
			if(semTake(semUartRecvFormGPSTask,WAIT_FOREVER)==OK)
			{
				printf("UartRecvFormGPSTask start::::\r\n");
				
				int fd = 0;
				int RxCom = 2;
				int ret = 0;				
				u8 temp_buf[2048] = {0};
				int msg_length = 0;
				struct timeval timeout;							
				char *ptr1 = "";
				char *ptr2 = "";
			
				/* �򿪽��մ��� */
				fd = open(g_ExtComName[RxCom], O_RDWR, 0);
				if (fd == ERROR)
				{
					printf("Open %s COM failed!\n", g_ExtComName[RxCom]);
					return;
				}
				/* ���ô��ڲ��� */				
				ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8 );
				ret += ioctl(fd, FIOBAUDRATE, GPS_COM_BAUD_RATE);   /* ������ */
				ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
			    ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */
							
				/* ��ӡ�������� */
				/* ��ʱ��ȡģʽ */
				/* ���ó�ʱʱ�� */
				timeout.tv_sec = 0;         /* 0 ��λs */
				timeout.tv_usec = 130000;   /* 30ms ��λus*/
				while(!msg_length)
				{
					msg_length = com_read_ex(fd, (char *)temp_buf, sizeof(temp_buf), &timeout);
					
				}
				
				ptr1 = strstr((char *)temp_buf, "$GNGGA");
				ptr2 = strstr((char *)temp_buf, "$GNVTG");
							
				if(ptr1 != NULL)
				Recv_From_GPS_GGA_Correct_Flag = Recv_From_GPS_GGA(temp_buf, msg_length);
				
				if(ptr2 != NULL)
				Recv_From_GPS_VTG_Correct_Flag = Recv_From_GPS_VTG(temp_buf, msg_length);
				
				taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
				close(fd);
				if(((Recv_From_GPS_GGA_Correct_Flag)==true)||((Recv_From_GPS_VTG_Correct_Flag)==true))
				{
					semGive(semUnpackGPSDataTask);
				}	
				
			}
		}	
}






void UartRecvFormBEIDOUTask(void)
{
	FOREVER
	{
		
		if(semTake(semUartRecvFormBEIDOUTask,WAIT_FOREVER)==OK)/*�����ݷ��͸������豸��*/
		{
			printf("UartRecvFormBEIDOUTask start::::\r\n");
			int fd = 0;
			int RxCom = 1;
			int ret = 0;
			u8 temp_buf[1024] = {0};
			int msg_length = 0;
			struct timeval timeout;
			char *ptr1 = "";
		

			/* �򿪽��մ��� */
			fd = open(g_ExtComName[RxCom], O_RDWR, 0);
			if (fd == ERROR)
			{
				printf("Open %s COM failed!\n", g_ExtComName[RxCom]);
				return;
			}
			/* ���ô��ڲ��� */
			/* ����λ8λ ֹͣλ1λ ��У�� ����ģʽ*/
			ret += ioctl(fd, SIO_HW_OPTS_SET, CLOCAL | CS8 );
			ret += ioctl(fd, FIOBAUDRATE, BEID_COM_BAUD_RATE);   /* ������ */
			ret += ioctl(fd, FIOSETOPTIONS, OPT_RAW);       /* ԭʼģʽOPT_RAW ��ģʽOPT_LINE �������ѡ�� */
			ret += ioctl(fd, FIOFLUSH, 0);                  /* ��ջ����� */

			/* ��ӡ�������� */
		    /* ��ʱ��ȡģʽ */
			/* ���ó�ʱʱ�� */
			timeout.tv_sec = 0;         /* 0 ��λs */
			timeout.tv_usec = 130000;   /* 130ms ��λus*/
			while(!msg_length)
			{
				msg_length = com_read_ex(fd, (char *)temp_buf, sizeof(temp_buf), &timeout);
			}			
			ptr1 = strstr((char *)temp_buf, "$BDTXR");
					
			
			if(ptr1 != NULL)
			Recv_From_BEIDOU_Correct_Flag = Recv_From_BEIDOU(temp_buf, msg_length);		
			
			
			taskDelay(sysClkRateGet()*0.03);   /*��ʱ30ms*/
			close(fd);
			if((Recv_From_BEIDOU_Correct_Flag)==true)
			{
				semGive(semUnpackBEIDOUDataTask);
			}
			
		}
	}	
}

bool Recv_From_IMU(u8 *temp, int length)
{
	if((0xCF == temp[0]))
			     return true;
			 else
				 return false; 
}

bool Recv_From_BMS_SS(u8 *temp, int length)
{
	if((0x03 == temp[1]) && (0x1A == temp[2]))/*Ҫ��ȡ���ֽ�����26��16������1A,2*N=2*13=26   */
			     return true;
			 else
				 return false; 
}
bool Recv_From_BMS_CS(u8 *temp, int length)
{
	if((0x03 == temp[1]) && (0x04 == temp[2]))/*Ҫ��ȡ���ֽ�����4��16������04,2*N=2*2=4    */
			     return true;
			 else
				 return false; 
}

bool Recv_From_LORA(u8 *temp, int length)
{ 
  u8 bytesum = 0;	
  bytesum = Check_Sum(temp, FromLORALength - 3);
 
  /*���ݳ����ж�*/
  if(length>71)
  {
	/*֡ͷ֡β��У����ж�*/ 
	if((temp[0] == 0x24) && (temp[1] == 0x43) && (temp[2] == 0x4b) && (temp[3] == 0x54) && (temp[4] == 0x48) &&      
								   (temp[70] == 0xFF) && (temp[71] == 0xFF)&& (temp[69] == bytesum))
	{
		UI_Channel_Selection_Down = 0x01;/*����loraͨ����־λ��*/	
		UI_Channel_Selection_Up = 0x01;/*����loraͨ����־λ��*/	
		return true;
	}	         
	else
	{
		return false; 
	}		
  }
  else
  {
	  return false; 
  }
}



bool Recv_From_PSD(u8 *temp, int length)
{
	/*֡ͷ�ж�*/
	if((0xAA == temp[0]) && (0x11 == temp[1]))
		     return true;
		 else
			 return false; 
}

bool Recv_From_DVL_BI(u8 *temp, int length)
{
	    u16 ii = 0, jj = 0;
		bool check_flag = false;
		
	if(length>0)/*���ݳ����ж�*/
	{
		for(ii = 0; ii < length; ii++)
		{
			/**************************************************** ����DVL��BI����*****************************************************/
			if((':' == temp[ii]) && ('B' == temp[ii+1])/*֡ͷ�ж��Լ�����λ���ж�*/
					&&('I' == temp[ii+2]))  
			{
				for(jj = 0; (jj < 240) && (ii+jj < length); jj++)
				{
					From_DVL_BI_Buf[jj]=temp[ii+jj];
				}	
				check_flag = true;
				Not_Recv_From_BI_DVL_No = 0;
				BI_Cal_Data_Flag = true;/*BI���� ��־λ����*/
			}
			else
			{
				continue;
			}
		}
		return check_flag;
	}
	else
	{
		Not_Recv_From_BI_DVL_No++;
		
	    return false; 
	}
}

bool Recv_From_DVL_BD(u8 *temp, int length)
{
	    u16 ii = 0, jj = 0;
		bool check_flag = false;
    if(length>0)/*���ݳ����ж�*/
	{	
		for(ii = 0; ii < length; ii++)
		{
			/**************************************************** ����DVL��BD����*****************************************************/
			if((':' == temp[ii]) && ('B' == temp[ii+1]) &&       /*֡ͷ�ж��Լ�����λ���ж�*/
			   ('D' == temp[ii+2]))
			{
				for(jj = 0; (jj < 240) && (ii+jj < length); jj++)
				{
					From_DVL_BD_Buf[jj]=temp[ii+jj];
				}	
				check_flag = true;
			}
			else
			{
				continue;
			}
		}
		return check_flag;
	}
    else
    {
   	  return false; 
    }   
    
    
}

bool Recv_From_DVL_WI(u8 *temp, int length)
{
	    u16 ii = 0, jj = 0;
		bool check_flag = false;
    if(length>0)/*���ݳ����ж�*/
	{	
		for(ii = 0; ii < length; ii++)
		{
			/**************************************************** ����DVL��WI����*****************************************************/
			if((':' == temp[ii]) && ('W' == temp[ii+1]) &&       /*֡ͷ�ж��Լ�����λ���ж�*/
			   ('I' == temp[ii+2]) )
			{
				for(jj = 0; (jj < 240) && (ii+jj < length); jj++)
				{
					From_DVL_WI_Buf[jj]=temp[ii+jj];
				}	
				check_flag = true;
				Not_Recv_From_WI_DVL_No = 0;
				WI_Cal_Data_Flag = true;/*WI���� ��־λ����*/
			}
			else
			{
				continue;
			}
		}
		return check_flag;
	}	
    else
    {
      Not_Recv_From_WI_DVL_No++;
      
   	  return false; 
    }
}

bool Recv_From_DVL_WD(u8 *temp, int length)
{
	    u16 ii = 0, jj = 0;
		bool check_flag = false;
	if(length>0)/*���ݳ����ж�*/
	{		
		for(ii = 0; ii < length; ii++)
		{
			/**************************************************** ����DVL��WD����*****************************************************/
			if((':' == temp[ii]) && ('W' == temp[ii+1]) &&         /*֡ͷ�ж��Լ�����λ���ж�*/
			   ('D' == temp[ii+2]) )
			{
				for(jj = 0; (jj < 240) && (ii+jj < length); jj++)
				{
					From_DVL_WD_Buf[jj]=temp[ii+jj];
				}	
				check_flag = true;
			}
			else
			{
				continue;
			}
		}
		return check_flag;
	}
	else
	{
		  return false; 
	}
	
}

bool Recv_From_DVL_ACK(u8 *temp, int length)
{
	    u16 ii = 0, jj = 0;
		bool check_flag = false;
	if(length>0)/*���ݳ����ж�*/
	{		
		for(ii = 0; ii< length; ii++)
		{
			/**************************************************** ����DVL��ACK����*****************************************************/
			if((':' == temp[ii]) && ('A' == temp[ii+1]) &&         /*֡ͷ�ж�*/
			   ('C' == temp[ii+2])&& ('K' == temp[ii+3]))
			{
				for(jj = 0; (jj < 240) && (ii+jj < length); jj++)
				{
					From_DVL_ACK_Buf[jj]=temp[ii+jj];
				}	
				check_flag = true;
			}
			else
			{
				continue;
			}
		}
		return check_flag;
	}
	else
	{
		return false; 
	}
	
	
}


bool Recv_From_GPS_GGA(u8 *temp, int length)
{
	u16 ii = 0, jj = 0;
	bool check_flag = false;
	
	for(ii = 0; ii+5 < length; ii++)
	{
		/**************************************************** ����GPGGA����*****************************************************/
		if(('$' == temp[ii]) && ('G' == temp[ii+1]) &&         /*֡ͷ�ж�*/
		   ('N' == temp[ii+2]) && ('G' == temp[ii+3]) &&
		   ('G' == temp[ii+4]) && ('A' == temp[ii+5]))
		{
			
			for(jj = 0; (jj < 240) && (ii+jj < length); jj++)
			{
				From_GPS_GGA_Buf[jj]=temp[ii+jj];
			}	
			check_flag = true;
		}
		else
		{
			continue;
		}
	}
	return check_flag;
}

bool Recv_From_GPS_VTG(u8 *temp, int length)
{
	u16 ii = 0, jj = 0;
		bool check_flag = false;
		
		for(ii = 0; ii+5 < length; ii++)
		{
			/**************************************************** ����GPVTG����*****************************************************/
			if(('$' == temp[ii]) && ('G' == temp[ii+1]) &&         /*֡ͷ�ж�*/
			   ('N' == temp[ii+2]) && ('V' == temp[ii+3]) &&
			   ('T' == temp[ii+4]) && ('G' == temp[ii+5]))
			{
				for(jj = 0; (jj < 240) && (ii+jj < length); jj++)
				{
					From_GPS_VTG_Buf[jj]=temp[ii+jj];
				}	
				check_flag = true;
			}
			else
			{
				continue;
			}
		}
		return check_flag;
}





bool Recv_From_BEIDOU(u8 *temp, int length)
{
	u16 ii = 0, jj = 0, kk=0;
	u8 bytesum = 0;	
	bool check_flag = false;	
	for(ii = 0; ii+5 < 1024; ii++)
	{	
		
		/**************************************************** ����BDTXR����*****************************************************/
		if(('$' == temp[ii]) && ('B' == temp[ii+1]) &&         /*֡ͷ�ж�*/
		   ('D' == temp[ii+2]) && ('T' == temp[ii+3])&& ('X' == temp[ii+4])&& ('R' == temp[ii+5]))
		{
			
			for(jj = 0; (jj < 57) && (ii+jj < length); jj++)
			{
				From_BEIDOU_Buf[jj] = temp[ii + jj];
			}		
			
			for(kk=22;kk<56;kk++)
		    {			
				From_BEIDOU_Buf_Self[kk-22] = From_BEIDOU_Buf[kk];				
				/*From_BEIDOU_Buf_Self[kk-22] = ASCII_to_HEX(From_BEIDOU_Buf_Self[kk-22]);*/
			}
				
			bytesum = Check_Sum(From_BEIDOU_Buf_Self, 34 - 3);/*34�����鳤�ȣ���ȥ3���Ǽ�ȥ��������֡β��У���λ*/
								
			/*У����жϣ��ۼӺ�*/
			if(bytesum != (From_BEIDOU_Buf_Self[31]))
			{
				printf("From_BEIDOU_Buf_Self check sum is wrong!::\n");
				printf("From_BEIDOU_Buf[22]:%2x From_BEIDOU_Buf[23]:%2x\n", From_BEIDOU_Buf[22], From_BEIDOU_Buf[23]);
				printf("From_BEIDOU_Buf_Self[0]:%2x From_BEIDOU_Buf_Self[1]:%2x\n", From_BEIDOU_Buf_Self[0], From_BEIDOU_Buf_Self[1]);
				printf("bytesum:%4x From_BEIDOU_Buf_Self[31]:%2x\n", bytesum, From_BEIDOU_Buf_Self[31]);	

			}	
			check_flag = true;
		}
		else
		{
			continue;
		}
	}

	return check_flag;
}


STATUS UdpSocketInit (const char * deviceIP, const u16 devicePort)
{
	short int UdpSockFd;   /*�ͻ����׽���*/
	u32 OptVal = 1;
    int ret;
    int to_send = 2048;
    
	struct sockaddr_in serverAddr;
	
	
	/*������Ч��У��*/
	if(INADDR_NONE == inet_addr(deviceIP))
	{
		printf("deviceIP error\n");
		return(ERROR);
	}
	
	/* �趨���ض˿ںź�IP */
	memset (&serverAddr, 0, sizeof(struct sockaddr_in));
	serverAddr.sin_family = AF_INET;
	serverAddr.sin_addr.s_addr = inet_addr(LocalIP); /* the local address */
	/*serverAddr.sin_port = htons(50000+devicePort);*/
	serverAddr.sin_port = htons(devicePort);
	serverAddr.sin_len = sizeof(serverAddr);
	
	/* �����׽��� */
	UdpSockFd = socket(AF_INET, SOCK_DGRAM, 0);
	if (UdpSockFd == ERROR)
	{
		ret = ERROR;
		printf("Create udp socket failed!\n");
		goto Exit;
	}
	
	
	
	  /* bind the socket���ﱾ����Ҫ�󶨵ģ��������в�ͨ�����ε��Ϳ���,����ip�뱻�󶨵��豸Ҫһ�£����ܰ󶨳ɹ���������൱�ڹ㲥*/
	
	ret=bind (UdpSockFd, (struct sockaddr*)&serverAddr, sizeof(serverAddr));
	if(ret < 0)
	{
		perror("bind");
		goto Exit;
	}
	

	/* ���÷��ͻ�������С */
	ret = setsockopt(UdpSockFd, SOL_SOCKET, SO_SNDBUF, (char *)&to_send, sizeof(to_send));
	if (ret < 0)
	{
		printf("setsockopt(SO_SNDBUF) failed!%d\n", ret);
		goto Exit;
	}

	/* ���ý��ջ�������С */
	ret = setsockopt(UdpSockFd, SOL_SOCKET, SO_RCVBUF, (char *)&to_send, sizeof(to_send));
	if (ret < 0)
	{
		printf("setsockopt(SO_RCVBUF) failed!%d\n", ret);
		goto Exit;
	}
	
   /* ���ý��ճ�ʱʱ��30ms,��ʱʱ�����������ͨ��������� */
	struct timeval timeout = {0,30};  
	ret = setsockopt(UdpSockFd, SOL_SOCKET, SO_RCVTIMEO, (char *)&timeout, sizeof(struct timeval));
	if (ret < 0)
	{
		printf("timeout setting for net recv faliured\r\n");
		goto Exit;
	}
	
	ioctl(UdpSockFd, (int)FIONBIO, (int)&OptVal);   /*���óɷ�������ʽ*/
		 
	 switch(devicePort)
	 {
	 	 case UIControllerPort:
	 		UIControllerFd = UdpSockFd;
	 		WIFI_Socket_Initial_Flag = true;
			UdpSockFd = 0;
			break;

	 	 case FMCUPort:
	 		MCUFd = UdpSockFd;
	 		FMCU_Socket_Initial_Flag = true;
	 		UdpSockFd = 0;
	 	    break;	
		
	 	 default:
	 		 break;	 
	 }
	 
	 Exit:
	 /* �ر��׽��� */
	 if (UdpSockFd != 0)
	 {
		 close(UdpSockFd);
		 return(ERROR);
	 }
	 return(OK);
}


void Perror(const char *s)  
{  
    perror(s);  
    exit(EXIT_FAILURE);  
} 

bool Lan_Recv_Data_Validity_check(u8 *check_head_buf, u8 *check_end_buf, u8 *receive_data, u16 received_len)
{
	  bool msg_process_flag = false;
	  u8 ii = 0;
	
	  char *temp_buf1 = "";   
	  char *temp_buf2 = "";	
	 
	   for(ii=received_len;ii<strlen((char *)receive_data); ii++)  
	   receive_data[ii] = '\0';
		
      temp_buf1 = strstr((char *)receive_data, (char *)check_head_buf);
	  temp_buf2 = strstr((char *)receive_data, (char *)check_end_buf);	
	  
	  
	 /* printf("receive_data:%s\n", receive_data);
	  printf("check_head_buf:%s\n", check_head_buf);
	  printf("check_end_buf:%s\n", check_end_buf);
	  printf("temp_buf1:%s\n", temp_buf1);
	  printf("temp_buf2:%s\n", temp_buf2);*/
	  
    if((temp_buf1!=NULL) && (temp_buf2!=NULL) && (strlen(temp_buf1) >= strlen(temp_buf2)))	
	{
		strncpy((char *)receive_data, (char *)temp_buf1, strlen(temp_buf1)-strlen(temp_buf2)+strlen((char *)check_end_buf));
		
	/*printf("---------------6\n");
	for(ii=0;*(receive_data+ii)!='\0';ii++)
	printf("%c",receive_data[ii]);
	printf("\n");*/
		
	msg_process_flag = true;
	}
	else
	{
		msg_process_flag = false;
		memset(receive_data, '\0', strlen((char *)receive_data));
	}
	  return msg_process_flag;
}
 

