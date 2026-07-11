#include <vxWorks.h>
#include <sysLib.h>
#include <taskLib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <logLib.h>
#include <fppLib.h>
#include <fioLib.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <ioLib.h>
#include <kernelLib.h>
#include <time.h>

#include "SailingBox.h"
#include "XMLFile.h"
#include "DataProcess.h"
#include "CtrlAlgorithm.h"

void DataStoreTask(void);
short int ReadBIOSRealTime(void);
STATUS setBiosTime(_BiosTimeSetting *buf);
unsigned long long FAT_Freespace(void);

_BIOSRealTime BIOS_RealTime; 
_BiosTimeSetting BiosTimeSetting;

bool New_Store_File_Flag = true;

bool UTC_Time_Calibrate_Falg = false;

void DataStoreTask(void)
{	
   FOREVER
   {
	  if(OK == semTake(semDataStoreTask,WAIT_FOREVER))
	  {
		printf("DataStoreTask start::::\r\n");	
		 
		static char SaveFileName[200] = "/ata0a/record/";
		char FileInfo[600];  /*一次存储的数据不能超过500个*/
		char SaveString[30];
		short int fd_SaveFile;
	/*	unsigned char *pBuf1;
		unsigned char *pBuf2;  */
		unsigned char ii = 0;
		
#if 0
		/*直接通过FXP新建一个record文件夹*/
		for(ii = 0; ii < 5; ii++)   
		{
			if(ioDefPathSet("/ata0a/record") == OK)  /*设置路劲*/
			{
				break;
			}
			else
			{
				logMsg("Set ioPath Failed \n", 0, 0, 0, 0, 0, 0);
				taskDelay(100);
			}
		} 
#endif
		
		

		FOREVER
		{			
			semTake(semDataStoreTask, WAIT_FOREVER);              /*解包一次数据，记录一次数据*/
			
			printf("semDataStore Task start:::::\n");
			
			if(true == New_Store_File_Flag)  /*1h创建一次新文件*/
			{
				New_Store_File_Flag = false;
				
				memset(SaveString, '\0', 30);  /*初始化为0*/
				
				ReadBIOSRealTime();

				sprintf(SaveString, "%04d", BIOS_RealTime.Year);
				strcat(SaveFileName, SaveString);

				sprintf(SaveString, "%02d", BIOS_RealTime.Month);
				strcat(SaveFileName, SaveString);

				sprintf(SaveString, "%02d", BIOS_RealTime.Day);
				strcat(SaveFileName, SaveString);

				sprintf(SaveString, "%02d", BIOS_RealTime.Hour);
				strcat(SaveFileName, SaveString);

				sprintf(SaveString, "%02d", BIOS_RealTime.Minute);
				strcat(SaveFileName, SaveString);

				sprintf(SaveString, "%02d", BIOS_RealTime.Second);
				strcat(SaveFileName, SaveString);

				strcat(SaveFileName, ".txt");
				strcat(SaveFileName, "\0");


				for(ii = 0; ii < 5; ii++)
				{		
					fd_SaveFile = creat(SaveFileName, O_RDWR);

					if(fd_SaveFile == ERROR)
					{
						logMsg("Open File LogFile.dat Failed 111111111111\n", 0, 0, 0, 0, 0, 0);
						taskDelay(100);
					}
					else
					{
						break;
					}

					if((fd_SaveFile == ERROR) && (ii >= 4))     /*尝试5次*/
					{							
						taskDelay(100);
					
						/*logMsg("creat file failed ii>5 \n",0,0,0,0,0,0);*/
						break;
					}
				}

				

				for(ii = 0; ii < 5; ii++)
				{
					if(close(fd_SaveFile) != ERROR)
					{
						break;
					}
					else
					{
						logMsg("close fd_SaveFile Failed 2222222222\n", 0, 0, 0, 0, 0, 0);
						taskDelay(20);
					}
				}
			}

			for(ii = 0; ii < 5; ii++)
			{
				fd_SaveFile = open(SaveFileName, O_RDWR, 0);

				if(fd_SaveFile != ERROR)
				{
					break;	
				}
				else
				{
					logMsg("open fd_SaveFile Failed 33333333333\n", 0, 0, 0, 0, 0, 0);
					taskDelay(10);
				}
			}
			
			
			/*存储下位机数据
			ReadBIOSRealTime();
			sprintf(FileInfo,"\r\n%02d:%02d:%02d::::\r\n", BIOS_RealTime.Hour, BIOS_RealTime.Minute, BIOS_RealTime.Second);
			lseek(fd_SaveFile,0, SEEK_END);
			write(fd_SaveFile, FileInfo, strlen(FileInfo));	
			
			taskDelay(10);	*/
			
			sprintf(FileInfo,"\r\n%03d %03d %03d %03f::::\r\n", DVL_Prase_Data.BI_X, DVL_Prase_Data.BI_Y, DVL_Prase_Data.BI_Z,DVL_Prase_Data.BI_V);
			sprintf(FileInfo,"\r\n%03d %03d ::::\r\n", DVL_Prase_Data.BD_Check, DVL_Prase_Data.BD_Height);
			
			sprintf(FileInfo,"\r\n%03d %03d %03d %03f::::\r\n", DVL_Prase_Data.WI_X, DVL_Prase_Data.WI_Y, DVL_Prase_Data.WI_Z,DVL_Prase_Data.WI_V);
			sprintf(FileInfo,"\r\n%03d %03d ::::\r\n", DVL_Prase_Data.WD_Check, DVL_Prase_Data.WD_Depth);
			
			lseek(fd_SaveFile,0, SEEK_END);
			write(fd_SaveFile, FileInfo, strlen(FileInfo));	
			/*存储wifi下行指令数据*//*有上位机数据时
			if(Not_Recv_From_WIFI_No < 5)  
			{
					sprintf(FileInfo, "%s %2x %2d %2d %2x %3d %3d %3d %3d %3d %2x %3d %3d %3d %3d %3d %3d %3d %2x %s\r\n", 
							UI_WIFI_Instruction.FromUI12_Head_BUF, 
							UI_WIFI_Instruction.FromUI12_ID, UI_WIFI_Instruction.FromUI12_Msg_Length, UI_WIFI_Instruction.FromUI12_Msg_Num, UI_WIFI_Instruction.FromUI12_Ctrl_Mode, 
							UI_WIFI_Instruction.FromUI12_Depth_Para1, UI_WIFI_Instruction.FromUI12_Depth_Para2, UI_WIFI_Instruction.FromUI12_Height_Para1, UI_WIFI_Instruction.FromUI12_Height_Para2,
							UI_WIFI_Instruction.FromUI12_Remain_Time, UI_WIFI_Instruction.FromUI12_Work_Cmd, UI_WIFI_Instruction.FromUI12_Motor_Speed1, UI_WIFI_Instruction.FromUI12_Motor_Speed2, 
							UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle, UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle, UI_WIFI_Instruction.FromUI12_RCD_UV_Set_Rud_Angle,
							UI_WIFI_Instruction.FromUI12_RCD_LV_Set_Rud_Angle, UI_WIFI_Instruction.FromUI12_Set_Course, UI_WIFI_Instruction.FromUI12_Check_Sum, UI_WIFI_Instruction.FromUI12_End_Buf
						);
				
				lseek(fd_SaveFile,0, SEEK_END);
				write(fd_SaveFile, FileInfo, strlen(FileInfo));	
			}
			taskDelay(10);*/
			
			
			/*存储wifi上行指令数据
			sprintf(FileInfo, "%s %3d %3d %2x %2x %3d %3d %3d %3d %3d %2x %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %3d %2x %s\r\n",				  
					To_UI12.ToUI12_Head_Buf,
					To_UI12.ToUI12_Msg_Length, To_UI12.ToUI12_Msg_Num, To_UI12.ToUI12_ID, To_UI12.ToUI12_Ctrl_Mode,
					To_UI12.ToUI12_Depth_Para1, To_UI12.ToUI12_Depth_Para2,
					To_UI12.ToUI12_Height_Para1, To_UI12.ToUI12_Height_Para2,
					To_UI12.ToUI12_Remain_Time, To_UI12.ToUI12_Work_Cmd, To_UI12.ToUI12_Motor_Speed1, To_UI12.ToUI12_Motor_Speed2,
			
					To_UI12.ToUI12_HL_Rud_Angle, To_UI12.ToUI12_HR_Rud_Angle, 
					To_UI12.ToUI12_VU_Rud_Angle, To_UI12.ToUI12_VL_Rud_Angle, To_UI12.ToUI12_Pres,
					To_UI12.ToUI12_Temp, To_UI12.ToUI12_Depth, To_UI12.ToUI12_IMU_Heading,
					To_UI12.ToUI12_IMU_Pitch, To_UI12.ToUI12_IMU_Roll, To_UI12.ToUI12_GPS_Heading, To_UI12.ToUI12_GPS_Velocity, 			
					To_UI12.ToUI12_DVL_Velocity, To_UI12.ToUI12_Height, To_UI12.ToUI12_Cal_Longitude, To_UI12.ToUI12_Cal_Latitude, 
			
					To_UI12.ToUI12_GPS_Longitude, To_UI12.ToUI12_GPS_Latitude, To_UI12.ToUI12_Total_Voltage, To_UI12.ToUI12_Total_Current, 
					To_UI12.ToUI12_SOC, To_UI12.ToUI12_SOH, To_UI12.ToUI12_SingleMax_Voltage, To_UI12.ToUI12_SingleMin_Voltage, 
					To_UI12.ToUI12_SingleMax_Temp, To_UI12.ToUI12_SingleMin_Temp, To_UI12.ToUI12_DevicePower_State, To_UI12.ToUI12_Cmd_State, 
					To_UI12.ToUI12_Sail_State, To_UI12.ToUI12_Sys_Abnorm_Inf, To_UI12.ToUI12_Dev_Abnorm_Inf, To_UI12.ToUI12_BMS_Abnorm_Inf, 
					To_UI12.ToUI12_Dev_Abnorm_Inf_Detail, To_UI12.ToUI12_Check_Sum, To_UI12.ToUI12_End_Buf
		
			);
			

	
			lseek(fd_SaveFile,0, SEEK_END);
			write(fd_SaveFile, FileInfo, strlen(FileInfo));	*/
			
			for(ii = 0; ii < 5; ii++)
			{
				if(close(fd_SaveFile) != ERROR)
				{
					break;
				}
				else
				{
					logMsg("close fd_SaveFile Failed 4444444444444\n", 0, 0, 0, 0, 0, 0);
					taskDelay(10);
				}
			}
		}
	  }
   }
}

short int ReadBIOSRealTime(void) 
{
    unsigned char uch = 0;  /*读取BIOS	实时时钟函数*/

    sysOutByte(RTC_INDEX, RTC_CENTURY); /* 世纪 */
    uch = sysInByte(RTC_DATA);
    BIOS_RealTime.Century = BCD_TO_BIN(uch);

    sysOutByte(RTC_INDEX, RTC_YEAR);    /* 年 */
    uch = sysInByte(RTC_DATA);
    BIOS_RealTime.Year = BCD_TO_BIN(uch);

    BIOS_RealTime.Year = BIOS_RealTime.Century * 100 + BIOS_RealTime.Year;

    sysOutByte(RTC_INDEX, RTC_MONTH);   /* 月 */
    uch = sysInByte(RTC_DATA);
    BIOS_RealTime.Month = BCD_TO_BIN(uch);

    sysOutByte(RTC_INDEX, RTC_DAY);     /* 日 */
    uch = sysInByte(RTC_DATA);
    BIOS_RealTime.Day = BCD_TO_BIN(uch);

    sysOutByte(RTC_INDEX, RTC_HOUR);    /* 时 */
    uch = sysInByte(RTC_DATA);
    BIOS_RealTime.Hour = BCD_TO_BIN(uch);

    sysOutByte(RTC_INDEX, RTC_MINUTE);  /* 分 */
    uch = sysInByte(RTC_DATA);
    BIOS_RealTime.Minute = BCD_TO_BIN(uch);

    sysOutByte(RTC_INDEX, RTC_SECOND);  /* 秒 */
    uch = sysInByte(RTC_DATA);
    BIOS_RealTime.Second = BCD_TO_BIN(uch);

    return 0;
}

/******************************************************************************
*                                                                             
* \brief  Function to read disk available space 
*                                                         
* \return  disk available space     
* 
* hy review 2017.11.4                                                                                                                                    
******************************************************************************/

unsigned long long FAT_Freespace(void) 
{
	struct statfs DiskInfo;
	unsigned long long blocksize;
	unsigned long long totalsize;
	unsigned long long freeDisk;
	unsigned long long availableDisk;
	
	statfs("/ata0a/",&DiskInfo);
	blocksize = DiskInfo.f_bsize;
	totalsize = blocksize*DiskInfo.f_blocks;
	/*printf("Total_size=%lluB =%lluKB =%lluMB =%lluGB\n",totalsize,totalsize>>10,totalsize>>20,totalsize>>30);*/
	
	freeDisk = DiskInfo.f_bfree*blocksize;/*剩余空间大小;*/
	availableDisk = DiskInfo.f_bavail*blocksize;/*可用空间大小*/
	/*printf("Disk_free=%lluMB =%lluGB\n",freeDisk>>20,freeDisk>>30); */
	/*printf("availableDisk=%lluMB =%lluGB\n",availableDisk>>20,availableDisk>>30);*/
	return availableDisk;
}


STATUS setBiosTime(_BiosTimeSetting *buf) /*设置新的时间到BIOS及系统，时间信息在tmBios中*/
{
  	unsigned char temp;
  	struct timespec tpp;
  	struct tm tmBios;
  	
  	/*test data*/
  	/*
  	(*buf).year = 2018;
  	(*buf).month = 8;
  	(*buf).day = 15;
  	(*buf).hour = 11;
	(*buf).min = 17;
	(*buf).sec = 15;
    */
	if((*buf).year > 1900)
		tmBios.tm_year = (*buf).year-1900;
	if(((*buf).month > 0) && ((*buf).month < 13))
		tmBios.tm_mon = (*buf).month - 1;
	if(((*buf).day > 0) && ((*buf).day < 32))
		tmBios.tm_mday = (*buf).day;
	
	if(((*buf).hour >= 0) && ((*buf).hour < 24))
		tmBios.tm_hour = (*buf).hour;
	if(((*buf).minute >= 0) && ((*buf).minute < 60))
		tmBios.tm_min = (*buf).minute;
	if(((*buf).second >= 0) && ((*buf).second < 60))
		tmBios.tm_sec = (*buf).second;
	
  	temp = tmBios.tm_sec/10*16+tmBios.tm_sec%10;
  	sysOutByte(0x70,0x00);
  	sysOutByte(0x71,temp);

  	temp = tmBios.tm_min/10*16+tmBios.tm_min%10;
  	sysOutByte(0x70,0x02);
  	sysOutByte(0x71,temp);

  	temp = tmBios.tm_hour/10*16+tmBios.tm_hour%10;
  	sysOutByte(0x70,0x04);
  	sysOutByte(0x71,temp);

  	/*
  	temp = tmBios.tm_mday/10*16+tmBios.tm_mday%10;
  	sysOutByte(0x70,0x07);
  	sysOutByte(0x71,temp);
	
  	temp = (tmBios.tm_mon+1)/10*16+(tmBios.tm_mon+1)%10;
  	sysOutByte(0x70,0x08);
  	sysOutByte(0x71,temp);

  	temp = (tmBios.tm_year-100)/10*16+(tmBios.tm_year-100)%10;
  	sysOutByte(0x70,0x09);
  	sysOutByte(0x71,temp);
  	*/
  	
  	tpp.tv_sec = mktime(&tmBios) + 3600;
  	tpp.tv_nsec = 0;
  	clock_settime(CLOCK_REALTIME, &tpp);  
  	return OK;
}
