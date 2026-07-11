#include "AgreedTerms.h"

typedef struct
{
	char *XML_name;  /*XML文件文件名*/
	char *attribute_name[1024]; /*属性名*/
	char *attribute_value[1024]; /*属性值*/
	char *element_name[1024]; /*元素名*/
	char *element_value[1024];  /*元素值*/
}_XMLData;


/*定点航行参数*/
typedef struct  
{	
	char *TaskNumber; /*任务编号*/
	u32 TotalTimeOut;  /*任务总时间*/	
	u8 TotalNumber; /*任务总点数*/	
	u8 TrackPoint[256]; /*目标点编号*/	
	double Longitude[256];   /*目标点经度*/
	double Latitude[256]; /*目标点纬度*/
	u8 Strategy[256];/*控制策略*/
	u16 Parameter[256];	/*控制参数*/
	u16 MotorSetSpeed[256]; /*主推转速*/
	u8 Device[256];/*设备上断电控制*/
}_FixedPoint_PathPlanning;

/*定向航行参数*/
typedef struct  
{	
	char *TaskNumber; /*任务编号*/
	u32 TotalTimeOut;  /*任务总时间*/	
	u8 TotalNumber; /*任务总点数*/	
	u8 TrackDirection[256]; /*目标方向编号*/	
	double Course[256];   /*航向*/
	double Duration[256]; /*持续时间*/
	u8 Strategy[256];/*控制策略*/
	u16 Parameter[256];	/*控制参数*/
	u16 MotorSetSpeed[256]; /*主推转速*/
	u8 Device[256];/*设备上断电控制*/
}_FixedDirection_PathPlanning;


extern void run_FixedPoint_xppTutorialAll(char *xmlFile);
extern void run_FixedDirection_xppTutorialAll(char *xmlFile);
extern void unpack_FixedPoint_XML(_XMLData *temp);
extern void unpack_FixedDirection_XML(_XMLData *temp);
extern void Auto_FixedPoint_Assignment(_FixedPoint_PathPlanning *temp);
extern void Auto_FixedDirection_Assignment(_FixedDirection_PathPlanning *temp);

extern _XMLData XMLData;
extern _FixedPoint_PathPlanning FixedPoint_PathPlanning;
extern _FixedDirection_PathPlanning FixedDirection_PathPlanning;

