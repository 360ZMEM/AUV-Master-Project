#include "AgreedTerms.h"

extern SEM_ID semDataStoreTask;

#define RTC_INDEX       0x70
#define RTC_DATA        0x71
#define RTC_CENTURY     0x32
#define RTC_YEAR        0x09
#define RTC_MONTH       0x08
#define RTC_DAY         0x07
#define RTC_HOUR        0x04
#define RTC_MINUTE      0x02
#define RTC_SECOND      0x00
#define BCD_TO_BIN(x) ((x) = ((x) & 0x0F) + (((x) >> 4) * 10))
#define BIN_TO_BCD(x) ((x) = (((x) / 10) << 4) + ((x) % 10))

typedef struct
{
	short int	Century;
	short int Year;
	short int Month;
	short int Day;
	short int Hour;
	short int Minute;
	short int Second;
} _BIOSRealTime;
extern  _BIOSRealTime BIOS_RealTime; 

typedef struct
{
	int year;
	int month;
	int day;
	int hour;
	int minute;
	int second;
}_BiosTimeSetting;

extern _BiosTimeSetting BiosTimeSetting;

extern void DataStoreTask(void);
extern STATUS setBiosTime(_BiosTimeSetting *buf);
extern short int ReadBIOSRealTime(void);
extern u16 Not_Recv_From_WIFI_No;
extern u16 Not_Recv_From_FMCU_No;
extern bool New_Store_File_Flag;
extern bool UTC_Time_Calibrate_Falg;
