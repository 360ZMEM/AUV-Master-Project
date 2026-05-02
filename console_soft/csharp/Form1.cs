using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using System.Runtime.InteropServices;
using System.Threading;
using System.Net.Sockets;
using System.Net;
using System.IO;
using System.Drawing.Drawing2D;
using System.Xml;
namespace Console
{
    public partial class Form1 : Form
    {
        // Form1 为上位机主控窗体，集中承担：
        // 1) 三链路通信（WiFi/无线电/北斗）的发送与接收；
        // 2) 协议打包/解包、校验、状态映射；
        // 3) 主界面和扩展界面 UI 刷新；
        // 4) 地图轨迹绘制、测距、自主定点航路编辑。
        // 说明：此文件采用 WinForms 事件驱动 + 手工字节协议处理风格，不做额外抽象层。
        public Form1()
        {
            InitializeComponent();
        }
        [DllImport("user32.dll", SetLastError = true)]
        public static extern bool RegisterHotKey(
            IntPtr hWnd,                //要定义热键的窗口的句柄
            int id,                     //定义热键ID（不能与其它ID重复）          
            KeyModifiers fsModifiers,   //标识热键是否在按Alt、Ctrl、Shift、Windows等键时才会生效
            Keys vk                     //定义热键的内容
            );

        [DllImport("user32.dll", SetLastError = true)]
        public static extern bool UnregisterHotKey(
            IntPtr hWnd,                //要取消热键的窗口的句柄
            int id                      //要取消热键的ID
            );

        //定义了辅助键的名称（将数字转变为字符以便于记忆，也可去除此枚举而直接使用数值）
        [Flags()]
        public enum KeyModifiers
        {
            None = 0,
            Alt = 1,
            Ctrl = 2,
            Shift = 4,
            WindowsKey = 8
        }

        [DllImport("user32.dll")]
        public static extern bool ReleaseCapture();
        [DllImport("user32.dll")]
        public static extern bool SendMessage(IntPtr hwnd, int wMsg, int wParam, int IParam);
        public const int WM_SYSCOMMAND = 0x0112;
        public const int SC_MOVE = 0xF010;
        public const int HTCAPYION = 0x0002;

        String IP_STRING_Console = "192.168.0.11";//操控台ip  //水面集控子系统（操控台） IP 地址： 192.168.0.11，端口号暂定6000
        int PORT_Console = 21;//操控台端口

        String IP_STRING_AUV = "192.168.0.101";//中央控制单元 IP 地址： 192.168.0.1，端口号暂定5000
        int PORT_AUV = 52364;
        float picM = 0.25F;
        bool flag_distance = false;//测距标志位
        PointF ruleStartPosition;//测量开始点
        PointF ruleEndPosition;//测量结束点
        struct AutoFixedPoint
        {
            public double Longitude;//经度
            public double Lat;//纬度
            public Byte Control_Strategy;//航控策略--0定深 1定高
            public float Control_Param;//航控参数
            public Int16 Motor_Speed;//主推转速
            public Byte Device_Control;//设备控制
        };
        List<AutoFixedPoint> Autofixedpoint = new List<AutoFixedPoint>();
        bool flag_autofixedpoint = false;//自主定点选点
        int autofixedpointNUM = 0;

        private UdpClient udp_send_recv;
        public Form2 Form_extend = null;
        public Form3 Form_set = null;
        IPEndPoint remoteipport = null;
        private Byte[] SEND = new Byte[72];
        Byte frame = 0;
        Thread thread_rec = null;//wifi接收线程
        Byte[] RECEV = null;//潜航体接收数据
        bool flag_BDSEND = false;//北斗是否发送标志
        Byte cnt_65s=0;//65秒计数
        Byte[] SEND_BD = new Byte[34];//北斗发送字节数组
        Byte frame_BD = 0;//北斗发送报文序号
        Byte[] RECEV_BD = null;//北斗接收数据字节数组

        float CourseAngle_AUV = 0.0F;
        double LONG_AUV = 0.0;
        double LAT_AUV = 0.0;
        Queue<PointF> Queue_GPS = new Queue<PointF>();//GPS队列
        Queue<PointF> Queue_GPS_CALC = new Queue<PointF>();//航位推算GPS队列
        double MapOriginLon=110.123;//初始经度
        double MapOriginLat=31.03;//初始纬度
        bool flag_first = true;
        public struct Preferences//首选项结构体
        {
            public Byte Objaddress;//目标地址
            public Byte Workmode;//工作模式
            public UInt16 DepthOutofrangeProtectParameter1;//航行超深保护参数1
            public UInt16 DepthOutofrangeProtectParameter2;//航行超深保护参数2
            public UInt16 BottomOutofrangeProtectParameter1;//离底超限保护参数1
            public UInt16 BottomOutofrangeProtectParameter2;//离底超限保护参数2
            public UInt16 Presettime;//预设时间
            public Int16 SpareParameter1;//备用参数1
            public Int16 SpareParameter2;//备用参数2
            public Int32 ReturnLong;//回航经度
            public Int32 ReturnLat;//回航纬度
        };
        public Preferences preferences;//实例化首选项结构体
        public Byte work_instruct = 0x00;//下发指令缓存
        public Byte ComMode = 0;//1-无线电串口 2-wifi 3-北斗串口
        public Int16 MotorSpeed1;//电机转速1
        public Int16 MotorSpeed2;//电机转速2
        public Int16 RudderAngle_LH;//左水平舵角
        public Int16 RudderAngle_RH;//右水平舵角
        public Int16 RudderAngle_UV;//上垂直舵角 Upper vertical rudder angle
        public Int16 RudderAngle_LV;//下垂直舵角 Lower vertical rudder angle
        public UInt16 OrientationAngle;//定向角度
        public Int32 Parameter1;//调参1
        public Int32 Parameter2;//调参2
        public Int32 Parameter3;//调参3
        public Int32 Parameter4;//调参4
        public Int16 Parameter5;//调参5
        public Int16 Parameter6;//调参6
        public Int16 Parameter7;//调参7
        public Int16 Parameter8;//调参8
        public Int16 Parameter9;//调参9
        public Int16 Parameter10;//调参10
        public Int16 Parameter11;//调参11
        public Int16 Parameter12;//调参12

        //HEX 转换成 ASCII
        Byte HEX_to_ASCII(Byte hex)
        {
            Byte sum;
            if (hex <= 0x09)
                sum = (Byte)(hex + 0x30);
            else
                sum = (Byte)(hex + 0x37);
            return sum;
        }//异或验证
        Byte Data_XOR(Byte[] data, Byte num)
        {
            Byte xor, i;
            xor = data[0];
            if (data.Length == 0)
            {
                return 0;
            }
            else
            {
                for (i = 1; i < num; i++)
                    xor = (Byte)(xor ^ data[i]);
            }
            return xor;
        }
        // Dest_ICnum[] 3 位接收者北斗卡号
        // BW_Data[] 所要发送的报文内容
        // Len_BW 报文长度
        Byte[] Dest_ICnum_gd = new Byte[3];
        UInt32 Dest_ADDR = 0;
        Byte CCTXA(Byte[] Dest_ICnum, Byte[] BW_Data, Byte Len_BW)
        {
            Byte return_data = 0;
            Byte[] CCTXA = new Byte[256];
            Byte i, j = 0;
            UInt32 RD21_dest_ICnum; //定义接收卡号
            Byte RD21_Temp_H, RD21_Temp_L;
            Byte[] RD21_Temp_CRC = new Byte[256];
            Byte RD21_Temp_CRC_H, RD21_Temp_CRC_L;
            RD21_dest_ICnum = (UInt32)(Dest_ICnum[0] * 256 * 256 + Dest_ICnum[1] * 256 + Dest_ICnum[2]);
            CCTXA[0] = (Byte)'$';
            CCTXA[1] = (Byte)'C';
            CCTXA[2] = (Byte)'C';
            CCTXA[3] = (Byte)'T';
            CCTXA[4] = (Byte)'X';
            CCTXA[5] = (Byte)'A';
            CCTXA[6] = (Byte)',';
            CCTXA[7] = (Byte)((RD21_dest_ICnum / 1000000) + '0');
            CCTXA[8] = (Byte)((RD21_dest_ICnum % 1000000) / 100000 + '0');
            CCTXA[9] = (Byte)(((RD21_dest_ICnum % 1000000) % 100000) / 10000 + '0');
            CCTXA[10] = (Byte)((((RD21_dest_ICnum % 1000000) % 100000) % 10000) / 1000 + '0');
            CCTXA[11] = (Byte)(((((RD21_dest_ICnum % 1000000) % 100000) % 10000) % 1000) / 100 + '0');
            CCTXA[12] = (Byte)((((((RD21_dest_ICnum % 1000000) % 100000) % 10000) % 1000) % 100) / 10 + '0');
            CCTXA[13] = (Byte)((((((RD21_dest_ICnum % 1000000) % 100000) % 10000) % 1000) % 100) % 10 + '0');
            CCTXA[14] = (Byte)',';
            CCTXA[15] = (Byte)'1';
            CCTXA[16] = (Byte)',';
            CCTXA[17] = (Byte)'2';
            CCTXA[18] = (Byte)',';
            CCTXA[19] = (Byte)'A';
            CCTXA[20] = (Byte)'4';
            for (i = 0; i < Len_BW; i++)
            {
                RD21_Temp_H = (Byte)(BW_Data[i] >> 4);
                CCTXA[21 + i * 2] = HEX_to_ASCII(RD21_Temp_H);
                RD21_Temp_L = (Byte)(BW_Data[i] << 4);
                RD21_Temp_L = (Byte)(RD21_Temp_L >> 4);
                CCTXA[22 + i * 2] = HEX_to_ASCII(RD21_Temp_L);
            }
            //j = 0;
            for (i = 0; i < 20 + Len_BW * 2; i++)//校验不算开头的$
                RD21_Temp_CRC[i] = CCTXA[i + 1];
            RD21_Temp_CRC[20 + Len_BW * 2] = Data_XOR(RD21_Temp_CRC, (Byte)(20 + Len_BW * 2));
            RD21_Temp_CRC_H = (Byte)(RD21_Temp_CRC[20 + Len_BW * 2] >> 4);
            RD21_Temp_CRC_L = (Byte)(RD21_Temp_CRC[20 + Len_BW * 2] << 4);
            RD21_Temp_CRC_L = (Byte)(RD21_Temp_CRC_L >> 4);
            CCTXA[20 + Len_BW * 2 + 1] = (Byte)'*';
            CCTXA[20 + Len_BW * 2 + 2] = HEX_to_ASCII(RD21_Temp_CRC_H);
            CCTXA[20 + Len_BW * 2 + 3] = HEX_to_ASCII(RD21_Temp_CRC_L);
            CCTXA[20 + Len_BW * 2 + 4] = 0x0D;
            CCTXA[20 + Len_BW * 2 + 5] = 0x0A;
            if (serialPort_BD.IsOpen)
                serialPort_BD.Write(CCTXA, 0, 20 + Len_BW * 2 + 5 + 1);
            //USART_PutStr(USART1,$CCTXA,20+Len_BW*2+5+1); //送入串口
            return return_data;
        }
        // 处理全局热键：Ctrl+Alt+B 打开 groupBox1，Ctrl+Alt+N 关闭 groupBox1。
        private void ProcessHotkey(Message m) //按下设定的键时调用该函数
        {
            //IntPtr //IntPtr用于表示指针或句柄的平台特定类型
            //MessageBox.Show(id.ToString());
            int sid = m.WParam.ToInt32();
            //MessageBox.Show(sid.ToString());
            switch (sid)
            {
                case 100://ctrl+alt+B
                    groupBox1.Enabled = true;
                    break;
                case 200://ctrl+alt+N
                    groupBox1.Enabled = false;
                    break;
                default:
                    break;
            }
        }
        //重写WndProc()方法，通过监视系统消息，来调用过程
        // 捕获系统消息并拦截热键消息，转交 ProcessHotkey 处理。
        protected override void WndProc(ref Message m)//监视Windows消息
        {
            const int WM_HOTKEY = 0x0312;//如果m.Msg的值为0x0312那么表示用户按下了热键
            switch (m.Msg)
            {
                case WM_HOTKEY:
                    ProcessHotkey(m);//按下热键时调用ProcessHotkey()函数
                    break;
            }
            base.WndProc(ref m); //将系统消息传递自父类的WndProc
        }
        
        // 主窗体启动初始化：
        // - 注册热键
        // - 读取 port_set.txt / param.txt
        // - 初始化 72 字节发送缓冲与 34 字节北斗缓冲
        // - 启动 WiFi 接收线程与定时器
        private void Form1_Load(object sender, EventArgs e)
        {
            Dest_ADDR = 0989564;//北斗发送地址--固定
            Dest_ICnum_gd[0] = (Byte)(Dest_ADDR >> 16);//Dest_ICnum_gd用三个字节来表示
            Dest_ICnum_gd[1] = (Byte)(Dest_ADDR>>8);
            Dest_ICnum_gd[2] = (Byte)Dest_ADDR;
            RegisterHotKey(Handle, 100, KeyModifiers.Alt | KeyModifiers.Ctrl, Keys.B);//热键为Alt+CTRL+B  注册热键
            RegisterHotKey(Handle, 200, KeyModifiers.Alt | KeyModifiers.Ctrl, Keys.N);//热键为Alt+CTRL+N  注册热键

            toolStripStatusLabel1.Text = "工作指令接收反馈区域";//工作指令接收反馈区域
            //开机读取端口配置文件
            using (StreamReader sr = new StreamReader(Application.StartupPath.ToString() + @"\port_set.txt"))//读取端口配置文件
            {
                String line;
                line = sr.ReadLine();//读取第1行
                serialPort_Radio.PortName = line.TrimEnd('\n');

                line = sr.ReadLine();//读取2行
                serialPort_BD.PortName = line.TrimEnd('\n');

                line = sr.ReadLine();//读取3行
                IP_STRING_Console = line.TrimEnd('\n');

                line = sr.ReadLine();//读取4行
                PORT_Console = Convert.ToInt32(line);

                line = sr.ReadLine();//读取5行
                IP_STRING_AUV = line.TrimEnd('\n');

                line = sr.ReadLine();//读取6行
                PORT_AUV = Convert.ToInt32(line);
                sr.Close();
            }

            IPEndPoint localipport = new IPEndPoint(IPAddress.Parse(IP_STRING_Console), PORT_Console);//水面集控子系统（操控台） IP 地址： 192.168.0.11，端口号暂定6000
            udp_send_recv = new UdpClient(localipport);
            remoteipport = new IPEndPoint(IPAddress.Parse(IP_STRING_AUV), PORT_AUV);//中央控制单元 IP 地址： 192.168.0.1，端口号暂定5000

            using (StreamReader sr = new StreamReader(Application.StartupPath.ToString()+@"\param.txt"))//读取参数文件
            {
                   String line;
                   line = sr.ReadLine();//读取第1行
                   preferences.Objaddress = Convert.ToByte(line);
                   comboBox1.SelectedIndex = (preferences.Objaddress - 1);

                   line = sr.ReadLine();//读取2行
                   preferences.Workmode=Convert.ToByte(line);
                   comboBox2.SelectedIndex = preferences.Workmode;

                   line = sr.ReadLine();//读取3行
                   preferences.DepthOutofrangeProtectParameter1 = Convert.ToUInt16(line);
                   textBox1.Text = preferences.DepthOutofrangeProtectParameter1.ToString();

                   line = sr.ReadLine();//读取4行
                   preferences.DepthOutofrangeProtectParameter2 = Convert.ToUInt16(line);
                   textBox2.Text = preferences.DepthOutofrangeProtectParameter2.ToString();

                   line = sr.ReadLine();//读取5行
                   preferences.BottomOutofrangeProtectParameter1 = Convert.ToUInt16(line);
                   textBox3.Text = preferences.BottomOutofrangeProtectParameter1.ToString();

                   line = sr.ReadLine();//读取6行
                   preferences.BottomOutofrangeProtectParameter2 = Convert.ToUInt16(line);
                   textBox4.Text = preferences.BottomOutofrangeProtectParameter2.ToString();

                   line = sr.ReadLine();//读取7行
                   preferences.Presettime = Convert.ToUInt16(line);
                   textBox5.Text = ((float)preferences.Presettime/10).ToString();

                   line = sr.ReadLine();//读取8行
                   preferences.SpareParameter1 = Convert.ToInt16(line);
                   textBox6.Text = ((float)preferences.SpareParameter1/10).ToString();

                   line = sr.ReadLine();//读取9行
                   preferences.SpareParameter2 = Convert.ToInt16(line);
                   textBox7.Text = ((float)preferences.SpareParameter2/10).ToString();

                   line = sr.ReadLine();//读取10行
                   preferences.ReturnLong = Convert.ToInt32(line);
                   textBox8.Text = ((double)preferences.ReturnLong / 1000000).ToString("F6");

                   line = sr.ReadLine();//读取11行
                   preferences.ReturnLat = Convert.ToInt32(line);
                   textBox9.Text = ((double)preferences.ReturnLat / 1000000).ToString("F6");
                   sr.Close();
            }
            /***********操控台发送至潜航体数据赋初值--72字节*******************************************************************************************/
            SEND[0] = 0x24;
            SEND[1] = 0x43;
            SEND[2] = 0x4B;
            SEND[3] = 0x54;
            SEND[4] = 0x48;//帧头至帧尾共72字节
            for (int i = 5; i <= 69; i++)
                SEND[i] = 0x00;
            SEND[70] = 0xFF;
            SEND[71] = 0xFF;

            /***************下发各值赋初值0*************************************************************************************************************************/
            MotorSpeed1 = 0;
            MotorSpeed2 = 0;
            RudderAngle_LH = 0;
            RudderAngle_RH = 0;
            RudderAngle_UV = 0;
            RudderAngle_LV = 0;
            OrientationAngle = 0;
            Parameter1 = 0;
            Parameter2 = 0;
            Parameter3 = 0;
            Parameter4 = 0;
            Parameter5 = 0;
            Parameter6 = 0;
            Parameter7 = 0;
            Parameter8 = 0;
            Parameter9 = 0;
            Parameter10 = 0;
            Parameter11 = 0;
            Parameter12 = 0;//下发各值赋初值0

            /*************操控台北斗发送数据赋初值--34字节********************************************************************************************/
            SEND_BD[0] = 0x24;
            SEND_BD[1] = 0x43;
            SEND_BD[2] = 0x4B;
            SEND_BD[3] = 0x54;
            SEND_BD[4] = 0x22;
            for (int jj = 5; jj < 30; jj++)
                SEND_BD[jj] = 0x00;
            SEND_BD[32] = 0xFF;
            SEND_BD[33] = 0xFF;
            //if(!serialPort_BD.IsOpen)
            //    serialPort_BD.Open();//北斗串口默认开启

            thread_rec = new Thread(THREAD_REC);//线程初始化
            thread_rec.Start();//启动线程
            wiFiToolStripMenuItem.Checked = true;//默认wifi

            timer1.Interval = 600;//0.6s
            timer1.Enabled = true;
            timer1.Start();//定时器0.6s并启动送

            timer2.Interval = 100;//原来是1000
            timer2.Enabled = true;
            timer2.Start();//1s----勾选北斗发送定时65秒并刷新指令发
        }
        //int cscs = 0;//测试一下
        // WiFi 接收线程：轮询 UDP 缓冲，按 145 字节帧格式做帧头帧尾与校验和校验。
        // 校验通过后更新 ComMode=2 并调用 display() 刷新界面。
        private void THREAD_REC()
        {//WiFi 中央控制单元->操控台
            IPEndPoint remoteipport1 = new IPEndPoint(IPAddress.Parse("192.168.0.101"), 21);
            while (true)
            {
                //String str = "";
                int n = udp_send_recv.Available;
                if (n > 0)
                {
                    RECEV = new Byte[n];
                    try
                    {
                        RECEV = udp_send_recv.Receive(ref remoteipport1);
                        if (RECEV.Length >= 145)//一帧完整的数据
                        {
                            if (RECEV[0] == 0x24 && RECEV[1] == 0x41 && RECEV[2] == 0x55 && RECEV[3] == 0x56 && RECEV[4] == 0x91 && RECEV[143] == 0xFF && RECEV[144] == 0xFF)//帧头帧尾数据长度正确
                            {
                                Byte checksum = 0;
                                for (int m = 0; m < 142; m++)
                                    checksum += RECEV[m];
                                if (RECEV[142] == (checksum & 0xFF))//校验正确
                                {
                                    ComMode = 2;//wifi接收
                                    display();
                                }
                            }
                        }
                    }
                    catch (Exception e)
                    {
                        //远程主机关闭有可能会报故障
                    }
                }
                Thread.Sleep(300);
            }
        }
        // 北斗分支数据显示：解析 RECEV_BD（72 字节压缩回传）并刷新主/扩展界面。
        // 注意：北斗字段布局与 WiFi/无线电不同，显示函数单独维护。
        private void display_BD()
        {
            this.Invoke(new Action(() =>
            {
                cscs++;
                richTextBox2.Text = cscs.ToString()+"北斗串口";//测试

                label74.Text = RECEV_BD[5].ToString();//报文编号
                label10.Text = RECEV_BD[6].ToString() + "号机器人";//本机地址
                switch (RECEV_BD[7])//工作模式
                {
                    case 0x00: label11.Text = "仅发送模式"; break;
                    case 0x01: label11.Text = "遥控模式"; break;
                    case 0x02: label11.Text = "自主定点航行"; break;
                    case 0x03: label11.Text = "自主定向航行"; break;
                    case 0x04: label11.Text = "回航模式"; break;
                    default: break;
                }
                label12.Text = ((UInt16)((RECEV_BD[8] << 8) + RECEV_BD[9])).ToString() + "m";//航行超深保护参数1当前数值
                label13.Text = ((UInt16)((RECEV_BD[10] << 8) + RECEV_BD[11])).ToString() + "m";//航行超深保护参数2当前数值
                label14.Text = ((UInt16)((RECEV_BD[12] << 8) + RECEV_BD[13])).ToString() + "m";//离底超限保护参数1当前数值
                label15.Text = ((UInt16)((RECEV_BD[14] << 8) + RECEV_BD[15])).ToString() + "m";//离底超限保护参数2当前数值
                label16.Text = (((UInt16)((RECEV_BD[16] << 8) + RECEV_BD[17])) * 0.1).ToString() + "min";//预设时间min
                label17.Text = (((Int16)((RECEV_BD[18] << 8) + RECEV_BD[19])) * 0.1).ToString();//备用参数1
                label18.Text = (((Int16)((RECEV_BD[20] << 8) + RECEV_BD[21])) * 0.1).ToString();//备用参数2
                toolStripStatusLabel1.Text = "--";
                label27.Text = (((Int32)((RECEV_BD[22] << 24) + (RECEV_BD[23] << 16) + (RECEV_BD[24] << 8) + RECEV_BD[25])) * 0.000001).ToString();//回航经度反馈数值
                label28.Text = (((Int32)((RECEV_BD[26] << 24) + (RECEV_BD[27] << 16) + (RECEV_BD[28] << 8) + RECEV_BD[29])) * 0.000001).ToString();//回航纬度反馈数值

                label76.Text = (((Int16)((RECEV_BD[30] << 8) + RECEV_BD[31])) * 0.001).ToString("F3") + "psi";//舱体内压
                label78.Text = ((SByte)RECEV_BD[32]).ToString() + "℃";//舱体温度
                label80.Text = (((UInt16)((RECEV_BD[33] << 8) + RECEV_BD[34])) * 0.1).ToString("F1") + "m";//航行深度

                //CourseAngle_AUV = (((UInt16)((RECEV_BD[35] << 8) + RECEV_BD[36])) * 0.1F);
                //label82.Text = CourseAngle_AUV.ToString("F1") + "°";//罗经航向
                label82.Text = (((Int16)((RECEV_BD[35] << 8) + RECEV_BD[36])) * 0.1).ToString("F1") + "°";//罗经航向
                label84.Text = (((Int16)((RECEV_BD[37] << 8) + RECEV_BD[38])) * 0.1).ToString("F1") + "°";//罗经俯仰
                label86.Text = (((Int16)((RECEV_BD[39] << 8) + RECEV_BD[40])) * 0.1).ToString("F1") + "°";//罗经横滚
                label88.Text = (((UInt16)((RECEV_BD[41] << 8) + RECEV_BD[42])) * 0.1).ToString("F1") + "°";//GPS航向
                label90.Text = (((UInt16)((RECEV_BD[43] << 8) + RECEV_BD[44])) * 0.1).ToString("F1") + "kn";//GPS航速
                label92.Text = (((Int16)((RECEV_BD[45] << 8) + RECEV_BD[46])) * 0.1).ToString("F1") + "kn";//DVL航速
                label94.Text = (((UInt16)((RECEV_BD[47] << 8) + RECEV_BD[48])) * 0.1).ToString("F1") + "m";//离底高度
                label97.Text = "--";//航位推算经度
                label98.Text = "--";//航位推算纬度

                LONG_AUV=(((Int32)((RECEV_BD[49] << 24) + (RECEV_BD[50] << 16) + (RECEV_BD[51] << 8) + RECEV_BD[52])) * 0.000001);
                LAT_AUV=(((Int32)((RECEV_BD[53] << 24) + (RECEV_BD[54] << 16) + (RECEV_BD[55] << 8) + RECEV_BD[56])) * 0.000001);
                if ((LONG_AUV != 0) && (LAT_AUV != 0))
                {
                    while (Queue_GPS.Count > 1000)
                        Queue_GPS.Dequeue();
                }
                Queue_GPS.Enqueue(new PointF((float)LONG_AUV,(float)LAT_AUV));

                label101.Text = LONG_AUV.ToString("F6") + "°";//GPS经度
                label102.Text = LAT_AUV.ToString("F6") + "°";//GPS纬度
                label104.Text = (((UInt16)((RECEV_BD[57] << 8) + RECEV_BD[58])) * 0.1).ToString("F1") + "V";//总电压
                label108.Text = RECEV_BD[59].ToString();//SOC
                pictureBox22.BackColor = Color.Transparent;
                pictureBox23.BackColor = Color.Transparent;
                pictureBox24.BackColor = Color.Transparent;
                pictureBox25.BackColor = Color.Transparent;

                if (Form_extend != null)
                {
                    Form_extend.label110.Text = RECEV_BD[60].ToString();//SOH
                    Form_extend.label20.Text = "--";//电机转速1
                    Form_extend.label21.Text = "--";//电机转速2
                    Form_extend.label23.Text = "--";//左水平舵角
                    Form_extend.label25.Text = "--";//右水平舵角
                    Form_extend.label27.Text = "--";//上垂直舵角
                    Form_extend.label28.Text = "--";//下垂直舵角
                    Form_extend.label46.Text = "--";//调参1当前值
                    Form_extend.label44.Text = "--";//调参2当前值
                    Form_extend.label42.Text = "--";//调参3当前值
                    Form_extend.label41.Text = "--";//调参4当前值
                    Form_extend.label40.Text = "--";//调参5当前值
                    Form_extend.label39.Text = "--";//调参6当前值
                    Form_extend.label37.Text = "--";//调参7当前值
                    Form_extend.label47.Text = "--";//调参8当前值
                    Form_extend.label49.Text = "--";//调参9当前值
                    Form_extend.label51.Text = "--";//调参10当前值
                    Form_extend.label52.Text = "--";//调参11当前值
                    Form_extend.label53.Text = "--";//调参12当前值
                    Form_extend.label97.Text = "--";//航位推算经度
                    Form_extend.label98.Text = "--";//航位推算纬度
                    Form_extend.label106.Text = "--";//总电流
                    Form_extend.label113.Text = "--";//单体最高电压
                    Form_extend.label116.Text = "--";//单体最低电压
                    Form_extend.label117.Text = "--";//单体最高温度
                    Form_extend.label118.Text = "--";//单体最低温度

                    Form_extend.richTextBox1.Text = "--";
                    Form_extend.richTextBox2.Text = "--";
                    Form_extend.toolStripStatusLabel1.Text = "--";
                    Form_extend.richTextBox3.Text = "--";
                }

                //任务状态反馈信息--主界面61-64
                if ((RECEV_BD[64] & 0x01) == 0x01)//自主定向航行任务开启
                    label22.Text = "开启";
                if ((RECEV_BD[64] & 0x02) == 0x02)//自主定向航行任务取消
                    label22.Text = "取消";
                if ((RECEV_BD[64] & 0x04) == 0x04)//自主定向航行任务完成
                    label22.Text = "完成";
                if ((RECEV_BD[64] & 0x08) == 0x08)//自主定向航行任务中断
                    label22.Text = "中断";
                if ((RECEV_BD[64] & 0x10) == 0x10)//自主定点航行任务开启
                    label23.Text = "开启";
                if ((RECEV_BD[64] & 0x20) == 0x20)//自主定点航行任务取消
                    label23.Text = "取消";
                if ((RECEV_BD[64] & 0x40) == 0x40)//自主定点航行任务完成
                    label23.Text = "完成";
                if ((RECEV_BD[64] & 0x80) == 0x80)//自主定点航行任务中断
                    label23.Text = "中断";

                if ((RECEV_BD[63] & 0x01) == 0x01)//回航任务开启  //回航任务反馈信息 仅3通道 北斗通信有效
                    label24.Text = "开启";
                if ((RECEV_BD[63] & 0x02) == 0x02)//回航任务取消
                    label24.Text = "取消";
                if ((RECEV_BD[63] & 0x04) == 0x04)//回航任务完成
                    label24.Text = "完成";
                if ((RECEV_BD[63] & 0x08) == 0x08)//回航任务中断
                    label24.Text = "中断";

                //系统异常信息反馈 65-68
                String str = "";
                if ((RECEV_BD[68] & 0x01) == 0x01)//舱体漏水报警
                    str += "舱体漏水报警\n";
                if ((RECEV_BD[68] & 0x02) == 0x02)//舱体温度超限报警
                    str += "舱体温度超限报警\n";
                if ((RECEV_BD[68] & 0x04) == 0x04)//舱体压力异常报警
                    str += "舱体压力异常报警\n";
                if ((RECEV_BD[68] & 0x08) == 0x08)//系统能源异常告警
                    str += "系统能源异常告警\n";
                if ((RECEV_BD[68] & 0x10) == 0x10)//设备能源异常告警
                    str += "设备能源异常告警\n";
                if ((RECEV_BD[68] & 0x20) == 0x20)//系统通信异常告警
                    str += "系统通信异常告警\n";
                if ((RECEV_BD[68] & 0x40) == 0x40)//设备状态异常告警
                    str += "设备状态异常告警\n";
                if ((RECEV_BD[68] & 0x80) == 0x80)//MCU → CPU 通信异常告警
                    str += "MCU→CPU通信异常告警\n";

                if ((RECEV_BD[67] & 0x01) == 0x01)//CPU→MCU 通信异常告警
                    str += "CPU→MCU通信异常告警\n";
                if ((RECEV_BD[67] & 0x02) == 0x02)//航行超深保护参数 1 告警
                    str += "航行超深保护参数1告警\n";
                if ((RECEV_BD[67] & 0x04) == 0x04)//航行超深保护参数 2 告警
                    str += "航行超深保护参数2告警\n";
                if ((RECEV_BD[67] & 0x08) == 0x08)//离底超限保护参数 1 告警
                    str += "离底超限保护参数1告警\n";
                if ((RECEV_BD[67] & 0x10) == 0x10)//离底超限保护参数 2 告警
                    str += "离底超限保护参数2告警\n";
                if ((RECEV_BD[67] & 0x20) == 0x20)//下潜超时告警
                    str += "下潜超时告警\n";
                if ((RECEV_BD[67] & 0x40) == 0x40)//航行超时告警
                    str += "航行超时告警\n";
                if ((RECEV_BD[67] & 0x80) == 0x80)//下潜姿态超限告警
                    str += "下潜姿态超限告警\n";

                if ((RECEV_BD[66] & 0x01) == 0x01)//航行姿态超限告警
                    str += "航行姿态超限告警\n";
                if ((RECEV_BD[66] & 0x02) == 0x02)//偏航距超限告警
                    str += "偏航距超限告警\n";
                richTextBox1.Text = str;
            }));
        }
        // 通用数据显示：解析 RECEV（145 字节）并刷新主界面、扩展界面、告警文本、地图数据队列。
        // 所有跨线程 UI 更新都在 Invoke 中执行，避免 WinForms 跨线程异常。
        private void display()
        {
            this.Invoke(new Action(() =>
            {
                cscs++;
                string sst = "";
                switch (ComMode)
                {
                    case 1: sst="无线电串口";break;
                    case 2: sst = "wifi"; break;
                    case 3: sst = "北斗串口"; break;
                    default: break;
                }
                //richTextBox2.Text = cscs.ToString()+sst;测试

                label74.Text = RECEV[5].ToString();//报文编号
                label10.Text=RECEV[6].ToString()+"号机器人";//本机地址
                switch (RECEV[7])//工作模式
                {
                    case 0x00: label11.Text = "仅发送模式"; break;
                    case 0x01: label11.Text = "遥控模式"; break;
                    case 0x02: label11.Text = "自主定点航行"; break;
                    case 0x03: label11.Text = "自主定向航行"; break;
                    case 0x04: label11.Text = "回航模式"; break;
                    default: break;
                }
                label12.Text = ((UInt16)((RECEV[8]<<8) + RECEV[9])).ToString()+"m";//航行超深保护参数1当前数值
                label13.Text = ((UInt16)((RECEV[10] << 8) + RECEV[11])).ToString() + "m";//航行超深保护参数2当前数值
                label14.Text = ((UInt16)((RECEV[12] << 8) + RECEV[13])).ToString() + "m";//离底超限保护参数1当前数值
                label15.Text = ((UInt16)((RECEV[14] << 8) + RECEV[15])).ToString() + "m";//离底超限保护参数2当前数值
                label16.Text = (((UInt16)((RECEV[16] << 8) + RECEV[17]))*0.1).ToString() + "min";//预设时间min
                label17.Text = (((Int16)((RECEV[18] << 8) + RECEV[19]))*0.1).ToString();//备用参数1
                label18.Text = (((Int16)((RECEV[20] << 8) + RECEV[21])) * 0.1).ToString();//备用参数2
                switch (RECEV[22])//工作指令接收反馈
                {
                    case 0x00: toolStripStatusLabel1.Text = "0x00:无意义"; break;
                    case 0x01: toolStripStatusLabel1.Text = "0x01:任务开启"; break;
                    case 0x02: toolStripStatusLabel1.Text = "0x02:任务取消"; break;
                    case 0x11: toolStripStatusLabel1.Text = "0x11:主推上电"; break;
                    case 0x12: toolStripStatusLabel1.Text = "0x12:主推断电"; break;
                    case 0x13: toolStripStatusLabel1.Text = "0x13:侧推上电"; break;
                    case 0x14: toolStripStatusLabel1.Text = "0x14:侧推断电"; break;
                    case 0x15: toolStripStatusLabel1.Text = "0x15:水平舵上电"; break;
                    case 0x16: toolStripStatusLabel1.Text = "0x16:水平舵断电"; break;
                    case 0x17: toolStripStatusLabel1.Text = "0x17:垂直舵上电"; break;
                    case 0x18: toolStripStatusLabel1.Text = "0x18:垂直舵断电"; break;
                    case 0x19: toolStripStatusLabel1.Text = "0x19:应急压载上电"; break;
                    case 0x20: toolStripStatusLabel1.Text = "0x20:应急压载断电"; break;
                    case 0x21: toolStripStatusLabel1.Text = "0x21:DVL上电"; break;
                    case 0x22: toolStripStatusLabel1.Text = "0x22:DVL断电"; break;
                    case 0x23: toolStripStatusLabel1.Text = "0x23:罗经上电"; break;
                    case 0x24: toolStripStatusLabel1.Text = "0x24:罗经断电"; break;
                    case 0x25: toolStripStatusLabel1.Text = "0x25:备用上电1"; break;
                    case 0x26: toolStripStatusLabel1.Text = "0x26:备用断电1"; break;
                    case 0x27: toolStripStatusLabel1.Text = "0x27:备用上电2"; break;
                    case 0x28: toolStripStatusLabel1.Text = "0x28:备用断电2"; break;
                    case 0x41: toolStripStatusLabel1.Text = "0x41:下潜测试"; break;
                    case 0x42: toolStripStatusLabel1.Text = "0x42:备用测试"; break;
                    case 0x51: toolStripStatusLabel1.Text = "0x51:参数调整开"; break;
                    case 0x52: toolStripStatusLabel1.Text = "0x52:参数调整关"; break;
                    case 0x53: toolStripStatusLabel1.Text = "0x53:备用开"; break;
                    case 0x54: toolStripStatusLabel1.Text = "0x54:备用关"; break;
                    case 0x61: toolStripStatusLabel1.Text = "0x61:查询指令1"; break;
                    case 0x62: toolStripStatusLabel1.Text = "0x62:查询指令2"; break;
                    case 0x71: toolStripStatusLabel1.Text = "0x71:定向航行开"; break;
                    case 0x72: toolStripStatusLabel1.Text = "0x72:定向航行关"; break;
                    case 0x73: toolStripStatusLabel1.Text = "0x73:备用开"; break;
                    case 0x74: toolStripStatusLabel1.Text = "0x74:备用关"; break;
                    case 0x81: toolStripStatusLabel1.Text = "0x81:载荷指令1"; break;
                    case 0x82: toolStripStatusLabel1.Text = "0x82:载荷指令2"; break;
                    case 0x83: toolStripStatusLabel1.Text = "0x83:载荷指令3"; break;
                    case 0x91: toolStripStatusLabel1.Text = "0x91:清除故障"; break;
                    case 0x92: toolStripStatusLabel1.Text = "0x92:初始化"; break;
                    case 0x93: toolStripStatusLabel1.Text = "0x93:备用指令1"; break;
                    case 0x94: toolStripStatusLabel1.Text = "0x94:备用指令2"; break;
                    default: break;
                }
                label76.Text = (((Int16)((RECEV[35] << 8) + RECEV[36])) * 0.001).ToString("F3") + "psi";//舱体内压
                label78.Text = ((SByte)RECEV[37]).ToString() + "℃";//舱体温度
                label80.Text = (((UInt16)((RECEV[38] << 8) + RECEV[39])) * 0.1).ToString("F1") + "m";//航行深度

                //CourseAngle_AUV = (((UInt16)((RECEV[72] << 8) + RECEV[73])) * 0.1F);
                //label82.Text = CourseAngle_AUV.ToString("F1") + "°";//罗经航向
                label82.Text = (((Int16)((RECEV[72] << 8) + RECEV[73])) * 0.1).ToString("F1") + "°"; ;//罗经航向
                label84.Text = (((Int16)((RECEV[74] << 8) + RECEV[75])) * 0.1).ToString("F1") + "°";//罗经俯仰
                label86.Text = (((Int16)((RECEV[76] << 8) + RECEV[77])) * 0.1).ToString("F1") + "°";//罗经横滚
                label88.Text = (((UInt16)((RECEV[78] << 8) + RECEV[79])) * 0.1).ToString("F1") + "°";//GPS航向
                label90.Text = (((UInt16)((RECEV[80] << 8) + RECEV[81])) * 0.1).ToString("F1") + "kn";//GPS航速
                label92.Text = (((Int16)((RECEV[82] << 8) + RECEV[83])) * 0.1).ToString("F1") + "kn";//DVL航速
                label94.Text = (((UInt16)((RECEV[84] << 8) + RECEV[85])) * 0.1).ToString("F1") + "m";//离底高度
                LONG_AUV=(((Int32)((RECEV[94] << 24) + (RECEV[95] << 16) + (RECEV[96] << 8) + RECEV[97])) * 0.000001);
                LAT_AUV=(((Int32)((RECEV[98] << 24) + (RECEV[99] << 16) + (RECEV[100] << 8) + RECEV[101])) * 0.000001);
                if((LONG_AUV!=0) && (LAT_AUV!=0) && flag_first)
                {
                    MapOriginLon = LONG_AUV;
                    MapOriginLat = LAT_AUV;
                    flag_first = false;
                }
                if ((LONG_AUV != 0) && (LAT_AUV != 0))
                {
                    while (Queue_GPS.Count > 1000)
                        Queue_GPS.Dequeue();
                    Queue_GPS.Enqueue(new PointF((float)LONG_AUV, (float)LAT_AUV));//压入队列画图
                }
                

                label101.Text = LONG_AUV.ToString("F6") + "°";//GPS经度
                label102.Text = LAT_AUV.ToString("F6") + "°";//GPS纬度
                label104.Text = (((UInt16)((RECEV[102] << 8) + RECEV[103])) * 0.1).ToString("F1") + "V";//总电压
                label108.Text = RECEV[106].ToString();//SOC


                LONG_AUV = (((Int32)((RECEV[86] << 24) + (RECEV[87] << 16) + (RECEV[88] << 8) + RECEV[89])) * 0.000001);
                LAT_AUV = (((Int32)((RECEV[90] << 24) + (RECEV[91] << 16) + (RECEV[92] << 8) + RECEV[93])) * 0.000001);
                label97.Text = LONG_AUV.ToString("F6") + "°";//航位推算经度
                label98.Text = LAT_AUV.ToString("F6") + "°";//航位推算纬度
                if ((LONG_AUV != 0) && (LAT_AUV != 0))
                {
                    while (Queue_GPS_CALC.Count > 1000)
                        Queue_GPS_CALC.Dequeue();
                    Queue_GPS_CALC.Enqueue(new PointF((float)LONG_AUV, (float)LAT_AUV));//压入队列画图
                }

                //操作反馈信息--主界面显示
                if ((RECEV[120] & 0x08) == 0x08)//系统故障清除完成
                    pictureBox22.BackColor = Color.Lime;
                else
                    pictureBox22.BackColor = Color.Transparent;
                if ((RECEV[120] & 0x10) == 0x10)//系统初始化完成
                    pictureBox23.BackColor = Color.Lime;
                else
                    pictureBox23.BackColor = Color.Transparent;
                if ((RECEV[120] & 0x20) == 0x20)//备用指令1执行
                    pictureBox24.BackColor = Color.Lime;
                else
                    pictureBox24.BackColor = Color.Transparent;
                if ((RECEV[120] & 0x40) == 0x40)//备用指令2执行
                    pictureBox25.BackColor = Color.Lime;
                else
                    pictureBox25.BackColor = Color.Transparent;
                //任务状态反馈信息--主界面
                if ((RECEV[125] & 0x01) == 0x01)//自主定向航行任务开启
                    label22.Text = "开启";
                if ((RECEV[125] & 0x02) == 0x02)//自主定向航行任务取消
                    label22.Text = "取消";
                if ((RECEV[125] & 0x04) == 0x04)//自主定向航行任务完成
                    label22.Text = "完成";
                if ((RECEV[125] & 0x08) == 0x08)//自主定向航行任务中断
                    label23.Text = "中断";
                if ((RECEV[125] & 0x10) == 0x10)//自主定点航行任务开启
                    label23.Text = "开启";
                if ((RECEV[125] & 0x20) == 0x20)//自主定点航行任务取消
                    label23.Text = "取消";
                if ((RECEV[125] & 0x40) == 0x40)//自主定点航行任务完成
                    label23.Text = "完成";
                if ((RECEV[125] & 0x80) == 0x80)//自主定点航行任务中断
                    label23.Text = "中断";
                //系统异常信息反馈
                String str = "";
                if ((RECEV[129] & 0x01) == 0x01)//舱体漏水报警
                    str += "舱体漏水报警\n";
                if ((RECEV[129] & 0x02) == 0x02)//舱体温度超限报警
                    str += "舱体温度超限报警\n";
                if ((RECEV[129] & 0x04) == 0x04)//舱体压力异常报警
                    str += "舱体压力异常报警\n";
                if ((RECEV[129] & 0x08) == 0x08)//系统能源异常告警
                    str += "系统能源异常告警\n";
                if ((RECEV[129] & 0x10) == 0x10)//设备能源异常告警
                    str += "设备能源异常告警\n";
                if ((RECEV[129] & 0x20) == 0x20)//系统通信异常告警
                    str += "系统通信异常告警\n";
                if ((RECEV[129] & 0x40) == 0x40)//设备状态异常告警
                    str += "设备状态异常告警\n";
                if ((RECEV[129] & 0x80) == 0x80)//MCU → CPU 通信异常告警
                    str += "MCU→CPU通信异常告警\n";

                if ((RECEV[128] & 0x01) == 0x01)//CPU→MCU 通信异常告警
                    str += "CPU→MCU通信异常告警\n";
                if ((RECEV[128] & 0x02) == 0x02)//航行超深保护参数 1 告警
                    str += "航行超深保护参数1告警\n";
                if ((RECEV[128] & 0x04) == 0x04)//航行超深保护参数 2 告警
                    str += "航行超深保护参数2告警\n";
                if ((RECEV[128] & 0x08) == 0x08)//离底超限保护参数 1 告警
                    str += "离底超限保护参数1告警\n";
                if ((RECEV[128] & 0x10) == 0x10)//离底超限保护参数 2 告警
                    str += "离底超限保护参数2告警\n";
                if ((RECEV[128] & 0x20) == 0x20)//下潜超时告警
                    str += "下潜超时告警\n";
                if ((RECEV[128] & 0x40) == 0x40)//航行超时告警
                    str += "航行超时告警\n";
                if ((RECEV[128] & 0x80) == 0x80)//下潜姿态超限告警
                    str += "下潜姿态超限告警\n";

                if ((RECEV[127] & 0x01) == 0x01)//航行姿态超限告警
                    str += "航行姿态超限告警\n";
                if ((RECEV[127] & 0x02) == 0x02)//偏航距超限告警
                    str += "偏航距超限告警\n";
                richTextBox1.Text = str;

                if (Form_extend != null)
                {
                    Form_extend.label20.Text = ((Int16)(((RECEV[23] << 8) + RECEV[24]))/10).ToString()+"rpm";//电机转速1
                    Form_extend.label21.Text = ((Int16)((RECEV[25] << 8) + RECEV[26])).ToString() + "rpm";//电机转速2
                    Form_extend.label23.Text = (((Int16)((RECEV[27] << 8) + RECEV[28]))*0.1).ToString("F1") + "°";//左水平舵角
                    Form_extend.label25.Text = (((Int16)((RECEV[29] << 8) + RECEV[30])) * 0.1).ToString("F1") + "°";//右水平舵角
                    Form_extend.label27.Text = (((Int16)((RECEV[31] << 8) + RECEV[32])) * 0.1).ToString("F1") + "°";//上垂直舵角
                    Form_extend.label28.Text = (((Int16)((RECEV[33] << 8) + RECEV[34])) * 0.1).ToString("F1") + "°";//下垂直舵角
                    Form_extend.label46.Text = (((Int32)((RECEV[40] << 24) + (RECEV[41] << 16) + (RECEV[42] << 8) + RECEV[43])) * 0.000001).ToString("F6");//调参1当前值
                    Form_extend.label44.Text = (((Int32)((RECEV[44] << 24) + (RECEV[45] << 16) + (RECEV[46] << 8) + RECEV[47])) * 0.000001).ToString("F6");//调参2当前值
                    Form_extend.label42.Text = (((Int32)((RECEV[48] << 24) + (RECEV[49] << 16) + (RECEV[50] << 8) + RECEV[51])) * 0.000001).ToString("F6");//调参3当前值
                    Form_extend.label41.Text = (((Int32)((RECEV[52] << 24) + (RECEV[53] << 16) + (RECEV[54] << 8) + RECEV[55])) * 0.000001).ToString("F6");//调参4当前值
                    Form_extend.label40.Text = (((Int16)((RECEV[56] << 8) + RECEV[57])) * 0.0001).ToString("F4");//调参5当前值
                    Form_extend.label39.Text = (((Int16)((RECEV[58] << 8) + RECEV[59])) * 0.0001).ToString("F4");//调参6当前值
                    Form_extend.label37.Text = (((Int16)((RECEV[60] << 8) + RECEV[61])) * 0.0001).ToString("F4");//调参7当前值
                    Form_extend.label47.Text = (((Int16)((RECEV[62] << 8) + RECEV[63])) * 0.0001).ToString("F4");//调参8当前值
                    Form_extend.label49.Text = (((Int16)((RECEV[64] << 8) + RECEV[65])) * 0.001).ToString("F3");//调参9当前值
                    Form_extend.label51.Text = (((Int16)((RECEV[66] << 8) + RECEV[67])) * 0.001).ToString("F3");//调参10当前值
                    Form_extend.label52.Text = (((Int16)((RECEV[68] << 8) + RECEV[69])) * 0.001).ToString("F3");//调参11当前值
                    Form_extend.label53.Text = (((Int16)((RECEV[70] << 8) + RECEV[71])) * 0.001).ToString("F3");//调参12当前值
                    Form_extend.label97.Text = (((Int32)((RECEV[86] << 24) + (RECEV[87] << 16) + (RECEV[88] << 8) + RECEV[89])) * 0.000001).ToString("F6")+"°";//航位推算经度
                    Form_extend.label98.Text = (((Int32)((RECEV[90] << 24) + (RECEV[91] << 16) + (RECEV[92] << 8) + RECEV[93])) * 0.000001).ToString("F6")+"°";//航位推算纬度
                    Form_extend.label106.Text = (((UInt16)((RECEV[104] << 8) + RECEV[105])) * 0.1).ToString("F1") + "A";//总电流
                    Form_extend.label110.Text = RECEV[107].ToString();//SOH
                    Form_extend.label113.Text = (((UInt16)((RECEV[108] << 8) + RECEV[109])) * 0.001).ToString("F3") + "V";//单体最高电压
                    Form_extend.label116.Text = (((UInt16)((RECEV[110] << 8) + RECEV[111])) * 0.001).ToString("F3") + "V";//单体最低电压
                    Form_extend.label117.Text = ((SByte)RECEV[112]).ToString() + "℃";//单体最高温度
                    Form_extend.label118.Text = ((SByte)RECEV[113]).ToString() + "℃";//单体最低温度

                    //设备上断电显示--扩展界面显示
                    if ((RECEV[117] & 0x01) == 0x01)//主推上断电
                        Form_extend.pictureBox1.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox1.BackColor = Color.Red;
                    if ((RECEV[117] & 0x02) == 0x02)//侧推上断电
                        Form_extend.pictureBox2.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox2.BackColor = Color.Red;
                    if ((RECEV[117] & 0x04) == 0x04)//水平左舵上断电
                        Form_extend.pictureBox3.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox3.BackColor = Color.Red;
                    if ((RECEV[117] & 0x08) == 0x08)//水平右舵上断电
                        Form_extend.pictureBox4.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox4.BackColor = Color.Red;
                    if ((RECEV[117] & 0x10) == 0x10)//垂直上舵上断电
                        Form_extend.pictureBox5.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox5.BackColor = Color.Red;
                    if ((RECEV[117] & 0x20) == 0x20)//垂直下舵上断电
                        Form_extend.pictureBox6.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox6.BackColor = Color.Red;
                    if ((RECEV[117] & 0x40) == 0x40)//主电源应急压载上断电
                        Form_extend.pictureBox7.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox7.BackColor = Color.Red;
                    if ((RECEV[117] & 0x80) == 0x80)//备用能源应急压载上断电
                        Form_extend.pictureBox8.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox8.BackColor = Color.Red;
                    if ((RECEV[116] & 0x01) == 0x01)//主电源通信模块上断电
                        Form_extend.pictureBox9.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox9.BackColor = Color.Red;
                    if ((RECEV[116] & 0x02) == 0x02)//备用能源通信模块上断电
                        Form_extend.pictureBox10.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox10.BackColor = Color.Red;
                    if ((RECEV[116] & 0x04) == 0x04)//多普勒计程仪（DVL）上断电
                        Form_extend.pictureBox22.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox22.BackColor = Color.Red;
                    if ((RECEV[116] & 0x08) == 0x08)//备用1上断电（无用置零）
                        Form_extend.pictureBox23.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox23.BackColor = Color.Red;
                    if ((RECEV[116] & 0x10) == 0x10)//备用2上断电（无用置零）
                        Form_extend.pictureBox24.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox24.BackColor = Color.Red;

                    //操作反馈信息--扩展界面显示
                    if ((RECEV[121] & 0x01) == 0x01)//下潜测试开启
                        Form_extend.pictureBox16.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox16.BackColor = Color.Transparent;
                    if ((RECEV[121] & 0x02) == 0x02)//备用测试开启
                        Form_extend.pictureBox15.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox15.BackColor = Color.Transparent;
                    if ((RECEV[121] & 0x04) == 0x04)//参数调整开启
                        Form_extend.pictureBox11.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox11.BackColor = Color.Transparent;
                    if ((RECEV[121] & 0x08) == 0x08)//备用调整开启
                        Form_extend.pictureBox12.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox12.BackColor = Color.Transparent;
                    if ((RECEV[121] & 0x10) == 0x10)//查询指令1执行
                        Form_extend.pictureBox18.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox18.BackColor = Color.Transparent;
                    if ((RECEV[121] & 0x20) == 0x20)//查询指令2执行
                        Form_extend.pictureBox17.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox17.BackColor = Color.Transparent;
                    if ((RECEV[121] & 0x40) == 0x40)//定向航行开启
                        Form_extend.pictureBox14.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox14.BackColor = Color.Transparent;
                    if ((RECEV[121] & 0x80) == 0x80)//备用开启
                        Form_extend.pictureBox13.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox13.BackColor = Color.Transparent;
                    if ((RECEV[120] & 0x01) == 0x01)//载荷指令1执行
                        Form_extend.pictureBox20.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox20.BackColor = Color.Transparent;
                    if ((RECEV[120] & 0x02) == 0x02)//载荷指令2执行
                        Form_extend.pictureBox19.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox19.BackColor = Color.Transparent;
                    if ((RECEV[120] & 0x04) == 0x04)//载荷指令3执行
                        Form_extend.pictureBox21.BackColor = Color.Lime;
                    else
                        Form_extend.pictureBox21.BackColor = Color.Transparent;

                    //设备状态异常信息反馈--扩展界面
                    String str1 = "";
                    if ((RECEV[133] & 0x01) == 0x01)//主推能源异常告警
                        str1 += "主推能源异常告警\n";
                    if ((RECEV[133] & 0x02) == 0x02)//侧推能源异常告警
                        str1 += "侧推能源异常告警\n";
                    if ((RECEV[133] & 0x04) == 0x04)//水平左舵能源异常告警
                        str1 += "水平左舵能源异常告警\n";
                    if ((RECEV[133] & 0x08) == 0x08)//水平右舵能源异常告警
                        str1 += "水平右舵能源异常告警\n";
                    if ((RECEV[133] & 0x10) == 0x10)//垂直上舵能源异常告警
                        str1 += "垂直上舵能源异常告警\n";
                    if ((RECEV[133] & 0x20) == 0x20)//垂直下舵能源异常告警
                        str1 += "垂直下舵能源异常告警\n";
                    if ((RECEV[133] & 0x40) == 0x40)//应急压载能源异常告警
                        str1 += "应急压载能源异常告警\n";
                    if ((RECEV[133] & 0x80) == 0x80)//DVL 能源异常告警
                        str1 += "DVL能源异常告警\n";

                    if ((RECEV[132] & 0x01) == 0x01)//备用 1 能源异常告警
                        str1 += "备用1能源异常告警\n";
                    if ((RECEV[132] & 0x02) == 0x02)//备用 2 能源异常告警
                        str1 += "备用2能源异常告警\n";
                    if ((RECEV[132] & 0x04) == 0x04)//主推通信异常告警
                        str1 += "主推通信异常告警\n";
                    if ((RECEV[132] & 0x08) == 0x08)//侧推通信异常告警
                        str1 += "侧推通信异常告警\n";
                    if ((RECEV[132] & 0x10) == 0x10)//水平左舵通信异常告警
                        str1 += "水平左舵通信异常告警\n";
                    if ((RECEV[132] & 0x20) == 0x20)//水平右舵通信异常告警
                        str1 += "水平右舵通信异常告警\n";
                    if ((RECEV[132] & 0x40) == 0x40)//垂直上舵通信异常告警
                        str1 += "垂直上舵通信异常告警\n";
                    if ((RECEV[132] & 0x80) == 0x80)//垂直下舵通信异常告警
                        str1 += "垂直下舵通信异常告警\n";

                    if ((RECEV[131] & 0x01) == 0x01)//DVL 通信异常告警
                        str1 += "DVL通信异常告警\n";
                    if ((RECEV[131] & 0x02) == 0x02)//罗经通信异常告警
                        str1 += "罗经通信异常告警\n";
                    if ((RECEV[131] & 0x04) == 0x04)//备用 1 通信异常告警
                        str1 += "备用1通信异常告警\n";
                    if ((RECEV[131] & 0x08) == 0x08)//备用 2 通信异常告警
                        str1 += "备用2通信异常告警\n";
                    if ((RECEV[131] & 0x10) == 0x10)//主推状态异常告警
                        str1 += "主推状态异常告警\n";
                    if ((RECEV[131] & 0x20) == 0x20)//侧推状态异常告警
                        str1 += "侧推状态异常告警\n";
                    if ((RECEV[131] & 0x40) == 0x40)//水平左舵状态异常告警
                        str1 += "水平左舵状态异常告警\n";
                    if ((RECEV[131] & 0x80) == 0x80)//水平右舵状态异常告警
                        str1 += "水平右舵状态异常告警\n";

                    if ((RECEV[130] & 0x01) == 0x01)//垂直上舵状态异常告警
                        str1 += "垂直上舵状态异常告警\n";
                    if ((RECEV[130] & 0x02) == 0x02)//垂直下舵状态异常告警
                        str1 += "垂直下舵状态异常告警\n";
                    if ((RECEV[130] & 0x04) == 0x04)//应急压载状态异常告警
                        str1 += "应急压载状态异常告警\n";
                    if ((RECEV[130] & 0x08) == 0x08)//DVL 状态异常告警
                        str1 += "DVL状态异常告警\n";
                    if ((RECEV[130] & 0x10) == 0x10)//罗经状态异常告警
                        str1 += "罗经状态异常告警\n";
                    if ((RECEV[130] & 0x20) == 0x20)//备用1状态异常告警
                        str1 += "备用1状态异常告警\n";
                    if ((RECEV[130] & 0x40) == 0x40)//频闪灯状态异常告警
                        str1 += "备用2状态异常告警\n";
                    if ((RECEV[130] & 0x80) == 0x80)//通信模块能源异常告警
                        str1 += "通信模块能源异常告警\n";
                    Form_extend.richTextBox1.Text = str1;

                    //能源状态异常详细信息反馈--扩展界面 134-137
                    String str2 = "";
                    if ((RECEV[137] & 0x01) == 0x01)//单体过压一级告警
                        str2 += "单体过压一级告警\n";
                    if ((RECEV[137] & 0x02) == 0x02)//系统过压一级告警
                        str2 += "系统过压一级告警\n";
                    if ((RECEV[137] & 0x04) == 0x04)//充电过流一级告警
                        str2 += "充电过流一级告警\n";
                    if ((RECEV[137] & 0x08) == 0x08)//单体欠压一级告警
                        str2 += "单体欠压一级告警\n";
                    if ((RECEV[137] & 0x10) == 0x10)//系统欠压一级告警
                        str2 += "系统欠压一级告警\n";
                    if ((RECEV[137] & 0x20) == 0x20)//放电过流一级告警
                        str2 += "放电过流一级告警\n";
                    if ((RECEV[137] & 0x40) == 0x40)//充电温度过高一级告警
                        str2 += "充电温度过高一级告警\n";
                    if ((RECEV[137] & 0x80) == 0x80)//充电温度过低一级告警
                        str2 += "充电温度过低一级告警\n";

                    if ((RECEV[136] & 0x01) == 0x01)//SOC 过低一级告警
                        str2 += "SOC过低一级告警\n";
                    if ((RECEV[136] & 0x02) == 0x02)//充电过流三级告警
                        str2 += "充电过流三级告警\n";
                    if ((RECEV[136] & 0x04) == 0x04)//功率温度过高一级告警
                        str2 += "功率温度过高一级告警\n";
                    if ((RECEV[136] & 0x08) == 0x08)//环境温度过高一级告警
                        str2 += "环境温度过高一级告警\n";
                    if ((RECEV[136] & 0x10) == 0x10)//环境温度过低一级告警
                        str2 += "环境温度过低一级告警\n";
                    if ((RECEV[136] & 0x20) == 0x20)//放电过流三级告警
                        str2 += "放电过流三级告警\n";
                    if ((RECEV[136] & 0x40) == 0x40)//放电温度过高一级告警
                        str2 += "放电温度过高一级告警\n";
                    if ((RECEV[136] & 0x80) == 0x80)//放电温度过低一级告警
                        str2 += "放电温度过低一级告警\n";

                    if ((RECEV[135] & 0x01) == 0x01)//单体过压二级告警
                        str2 += "单体过压二级告警\n";
                    if ((RECEV[135] & 0x02) == 0x02)//系统过压二级告警
                        str2 += "系统过压二级告警\n";
                    if ((RECEV[135] & 0x04) == 0x04)//充电过流二级告警
                        str2 += "充电过流二级告警\n";
                    if ((RECEV[135] & 0x08) == 0x08)//单体欠压二级告警
                        str2 += "单体欠压二级告警\n";
                    if ((RECEV[135] & 0x10) == 0x10)//系统欠压二级告警
                        str2 += "系统欠压二级告警\n";
                    if ((RECEV[135] & 0x20) == 0x20)//放电过流二级告警
                        str2 += "放电过流二级告警\n";
                    if ((RECEV[135] & 0x40) == 0x40)//充电温度过高二级告警
                        str2 += "充电温度过高二级告警\n";
                    if ((RECEV[135] & 0x80) == 0x80)//充电温度过低二级告警
                        str2 += "充电温度过低二级告警\n";

                    if ((RECEV[134] & 0x01) == 0x01)//SOC 过低二级告警
                        str2 += "SOC过低二级告警\n";
                    if ((RECEV[134] & 0x02) == 0x02)//充电过流三级告警
                        str2 += "充电过流三级告警\n";
                    if ((RECEV[134] & 0x04) == 0x04)//功率温度过高二级告警
                        str2 += "功率温度过高二级告警\n";
                    if ((RECEV[134] & 0x08) == 0x08)//环境温度过高二级告警
                        str2 += "环境温度过高二级告警\n";
                    if ((RECEV[134] & 0x10) == 0x10)//环境温度过低二级告警
                        str2 += "环境温度过低二级告警\n";
                    if ((RECEV[134] & 0x20) == 0x20)//放电过流三级告警
                        str2 += "放电过流三级告警\n";
                    if ((RECEV[134] & 0x40) == 0x40)//放电温度过高二级告警
                        str2 += "放电温度过高二级告警\n";
                    if ((RECEV[134] & 0x80) == 0x80)//放电温度过低二级告警
                        str2 += "放电温度过低二级告警\n";
                    Form_extend.richTextBox2.Text = str2;

                    switch (RECEV[22])//工作指令接收反馈
                    {
                        case 0x00: Form_extend.toolStripStatusLabel1.Text = "0x00:无意义"; break;
                        case 0x01: Form_extend.toolStripStatusLabel1.Text = "0x01:任务开启"; break;
                        case 0x02: Form_extend.toolStripStatusLabel1.Text = "0x02:任务取消"; break;
                        case 0x11: Form_extend.toolStripStatusLabel1.Text = "0x11:主推上电"; break;
                        case 0x12: Form_extend.toolStripStatusLabel1.Text = "0x12:主推断电"; break;
                        case 0x13: Form_extend.toolStripStatusLabel1.Text = "0x13:侧推上电"; break;
                        case 0x14: Form_extend.toolStripStatusLabel1.Text = "0x14:侧推断电"; break;
                        case 0x15: Form_extend.toolStripStatusLabel1.Text = "0x15:水平舵上电"; break;
                        case 0x16: Form_extend.toolStripStatusLabel1.Text = "0x16:水平舵断电"; break;
                        case 0x17: Form_extend.toolStripStatusLabel1.Text = "0x17:垂直舵上电"; break;
                        case 0x18: Form_extend.toolStripStatusLabel1.Text = "0x18:垂直舵断电"; break;
                        case 0x19: Form_extend.toolStripStatusLabel1.Text = "0x19:应急压载上电"; break;
                        case 0x20: Form_extend.toolStripStatusLabel1.Text = "0x20:应急压载断电"; break;
                        case 0x21: Form_extend.toolStripStatusLabel1.Text = "0x21:DVL上电"; break;
                        case 0x22: Form_extend.toolStripStatusLabel1.Text = "0x22:DVL断电"; break;
                        case 0x23: Form_extend.toolStripStatusLabel1.Text = "0x23:罗经上电"; break;
                        case 0x24: Form_extend.toolStripStatusLabel1.Text = "0x24:罗经断电"; break;
                        case 0x25: Form_extend.toolStripStatusLabel1.Text = "0x25:备用上电1"; break;
                        case 0x26: Form_extend.toolStripStatusLabel1.Text = "0x26:备用断电1"; break;
                        case 0x27: Form_extend.toolStripStatusLabel1.Text = "0x27:备用上电2"; break;
                        case 0x28: Form_extend.toolStripStatusLabel1.Text = "0x28:备用断电2"; break;
                        case 0x41: Form_extend.toolStripStatusLabel1.Text = "0x41:下潜测试"; break;
                        case 0x42: Form_extend.toolStripStatusLabel1.Text = "0x42:备用测试"; break;
                        case 0x51: Form_extend.toolStripStatusLabel1.Text = "0x51:参数调整开"; break;
                        case 0x52: Form_extend.toolStripStatusLabel1.Text = "0x52:参数调整关"; break;
                        case 0x53: Form_extend.toolStripStatusLabel1.Text = "0x53:备用开"; break;
                        case 0x54: Form_extend.toolStripStatusLabel1.Text = "0x54:备用关"; break;
                        case 0x61: Form_extend.toolStripStatusLabel1.Text = "0x61:查询指令1"; break;
                        case 0x62: Form_extend.toolStripStatusLabel1.Text = "0x62:查询指令2"; break;
                        case 0x71: Form_extend.toolStripStatusLabel1.Text = "0x71:定向航行开"; break;
                        case 0x72: Form_extend.toolStripStatusLabel1.Text = "0x72:定向航行关"; break;
                        case 0x73: Form_extend.toolStripStatusLabel1.Text = "0x73:备用开"; break;
                        case 0x74: Form_extend.toolStripStatusLabel1.Text = "0x74:备用关"; break;
                        case 0x81: Form_extend.toolStripStatusLabel1.Text = "0x81:载荷指令1"; break;
                        case 0x82: Form_extend.toolStripStatusLabel1.Text = "0x82:载荷指令2"; break;
                        case 0x83: Form_extend.toolStripStatusLabel1.Text = "0x83:载荷指令3"; break;
                        case 0x91: Form_extend.toolStripStatusLabel1.Text = "0x91:清除故障"; break;
                        case 0x92: Form_extend.toolStripStatusLabel1.Text = "0x92:初始化"; break;
                        case 0x93: Form_extend.toolStripStatusLabel1.Text = "0x93:备用指令1"; break;
                        case 0x94: Form_extend.toolStripStatusLabel1.Text = "0x94:备用指令2"; break;
                        default: break;
                    }

                    String str3 = "";//设备状态异常详细信息反馈 138-141
                    if ((RECEV[141] & 0x01) == 0x01)//水平左舵舵机过载
                        str3 += "水平左舵舵机过载\n";
                    if ((RECEV[141] & 0x02) == 0x02)//水平左舵舵机过流
                        str3 += "水平左舵舵机过流\n";
                    if ((RECEV[141] & 0x04) == 0x04)//水平左舵舵机过热
                        str3 += "水平左舵舵机过热\n";
                    if ((RECEV[141] & 0x08) == 0x08)//水平左舵舵机角度错误
                        str3 += "水平左舵舵机角度错误\n";
                    if ((RECEV[141] & 0x10) == 0x10)//水平左舵舵机过压欠压
                        str3 += "水平左舵舵机过压欠压\n";
                    if ((RECEV[141] & 0x20) == 0x20)//水平右舵舵机过载
                        str3 += "水平右舵舵机过载\n";
                    if ((RECEV[141] & 0x40) == 0x40)//水平右舵舵机过流
                        str3 += "水平右舵舵机过流\n";
                    if ((RECEV[141] & 0x80) == 0x80)//水平右舵舵机过热
                        str3 += "水平右舵舵机过热\n";

                    if ((RECEV[140] & 0x01) == 0x01)//水平右舵舵机角度错误
                        str3 += "水平右舵舵机角度错误\n";
                    if ((RECEV[140] & 0x02) == 0x02)//水平右舵舵机过压欠压
                        str3 += "水平右舵舵机过压欠压\n";
                    if ((RECEV[140] & 0x04) == 0x04)//垂直上舵舵机过载
                        str3 += "垂直上舵舵机过载\n";
                    if ((RECEV[140] & 0x08) == 0x08)//垂直上舵舵机过流
                        str3 += "垂直上舵舵机过流\n";
                    if ((RECEV[140] & 0x10) == 0x10)//垂直上舵舵机过热
                        str3 += "垂直上舵舵机过热\n";
                    if ((RECEV[140] & 0x20) == 0x20)//垂直上舵舵机角度错误
                        str3 += "垂直上舵舵机角度错误\n";
                    if ((RECEV[140] & 0x40) == 0x40)//垂直上舵舵机过压欠压
                        str3 += "垂直上舵舵机过压欠压\n";
                    if ((RECEV[140] & 0x80) == 0x80)//垂直下舵舵机过载
                        str3 += "垂直下舵舵机过载\n";

                    if ((RECEV[139] & 0x01) == 0x01)//垂直下舵舵机过流
                        str3 += "垂直下舵舵机过流\n";
                    if ((RECEV[139] & 0x02) == 0x02)//垂直下舵舵机过热
                        str3 += "垂直下舵舵机过热\n";
                    if ((RECEV[139] & 0x04) == 0x04)//垂直下舵舵机角度错误
                        str3 += "垂直下舵舵机角度错误\n";
                    if ((RECEV[139] & 0x08) == 0x08)//垂直下舵舵机过压欠压
                        str3 += "垂直下舵舵机过压欠压\n";
                    if ((RECEV[139] & 0x10) == 0x10)//主推堵转停止
                        str3 += "主推堵转停止\n";
                    if ((RECEV[139] & 0x20) == 0x20)//主推不达速
                        str3 += "主推不达速\n";
                    if ((RECEV[139] & 0x40) == 0x40)//主推霍尔错误
                        str3 += "主推霍尔错误\n";
                    //if ((RECEV[139] & 0x80) == 0x80)//无效置零
                    //    str3 += "充电温度过低二级告警\n";

                    //if ((RECEV[138] & 0x01) == 0x01)//无效置零
                    //    str3 += "无效置零\n";
                    //if ((RECEV[138] & 0x02) == 0x02)//无效置零
                    //    str3 += "无效置零\n";
                    if ((RECEV[138] & 0x04) == 0x04)//DVL 自检异常
                        str3 += "DVL自检异常\n";
                    if ((RECEV[138] & 0x08) == 0x08)//DVL对底无效
                        str3 += "DVL对底无效\n";
                    //if ((RECEV[138] & 0x10) == 0x10)//无效置零
                    //    str3 += "环境温度过低二级告警\n";
                    //if ((RECEV[138] & 0x20) == 0x20)//无效置零
                    //    str3 += "放电过流三级告警\n";
                    //if ((RECEV[138] & 0x40) == 0x40)//无效置零
                    //    str3 += "放电温度过高二级告警\n";
                    //if ((RECEV[138] & 0x80) == 0x80)//无效置零
                    //    str3 += "放电温度过低二级告警\n";
                    Form_extend.richTextBox3.Text = str3;
                }
            }));
        }
        // “确认”按钮：校验任务参数输入范围，写入 preferences，并持久化到 param.txt（固定 11 行）。
        private void button1_Click(object sender, EventArgs e)
        {//确认
            try
            {
                preferences.Objaddress = (Byte)(comboBox1.SelectedIndex + 1);//目标地址
                preferences.Workmode = (Byte)(comboBox2.SelectedIndex);//工作模式
                UInt16 tmp = Convert.ToUInt16(textBox1.Text);
                if (tmp >= 0 && tmp <= 1000)
                    preferences.DepthOutofrangeProtectParameter1 = tmp;
                else
                {
                    MessageBox.Show("航行超深保护参数1输入没有在0--1000米之内，请重新输入！");
                    return;
                }

                tmp = Convert.ToUInt16(textBox2.Text);
                if (tmp >= 0 && tmp <= 1000)
                    preferences.DepthOutofrangeProtectParameter2 = tmp;
                else
                {
                    MessageBox.Show("航行超深保护参数2输入没有在0--1000米之内，请重新输入！");
                    return;
                }

                tmp = Convert.ToUInt16(textBox3.Text);
                if (tmp >= 10 && tmp <= 300)
                    preferences.BottomOutofrangeProtectParameter1 = tmp;
                else
                {
                    MessageBox.Show("离底超限保护参数1输入没有在10--300米之内，请重新输入！");
                    return;
                }

                tmp = Convert.ToUInt16(textBox4.Text);
                if (tmp >= 5 && tmp <= 300)
                    preferences.BottomOutofrangeProtectParameter2 = tmp;
                else
                {
                    MessageBox.Show("离底超限保护参数2输入没有在5--300米之内，请重新输入！");
                    return;
                }

                float tmp1 = Convert.ToSingle(textBox5.Text);
                if (tmp1 >= 0 && tmp1 <= 6000)
                    preferences.Presettime = Convert.ToUInt16(tmp1 * 10);
                else
                {
                    MessageBox.Show("预设时间没有在0--6000分钟之内，请重新输入！");
                    return;
                }

                float tmp2 = Convert.ToSingle(textBox6.Text);//备用参数1
                if (tmp2 >= -3000 && tmp2 <= 3000)
                    preferences.SpareParameter1 = Convert.ToInt16(tmp2 * 10);
                else
                {
                    MessageBox.Show("备用参数1没有在-3000--3000之内，请重新输入！");
                    return;
                }

                tmp2 = Convert.ToSingle(textBox7.Text);//备用参数2
                if (tmp2 >= -3000 && tmp2 <= 3000)
                    preferences.SpareParameter2 = Convert.ToInt16(tmp2 * 10);
                else
                {
                    MessageBox.Show("备用参数2没有在-3000--3000之内，请重新输入！");
                    return;
                }

                double tmp3 = Convert.ToDouble(textBox8.Text);//回航经度
                if (tmp3 >= -180 && tmp3 <= 180)
                {
                    preferences.ReturnLong = Convert.ToInt32(tmp3 * 1000000);
                }
                else
                {
                    MessageBox.Show("回航经度没有在-180--180度之间，请重新输入！");
                    return;
                }

                tmp3 = Convert.ToDouble(textBox9.Text);//回航纬度
                if (tmp3 >= -90 && tmp3 <= 90)
                {
                    preferences.ReturnLat = Convert.ToInt32(tmp3 * 1000000);
                }
                else
                {
                    MessageBox.Show("回航纬度没有在-90--90度之间，请重新输入！");
                    return;
                }
                groupBox1.Enabled = false;

                //写入文件下次自动加载
                using (StreamWriter sw = new StreamWriter(Application.StartupPath.ToString()+@"\param.txt"))
                {
                    sw.WriteLine(preferences.Objaddress.ToString());
                    sw.WriteLine(preferences.Workmode.ToString());
                    sw.WriteLine(preferences.DepthOutofrangeProtectParameter1.ToString());
                    sw.WriteLine(preferences.DepthOutofrangeProtectParameter2.ToString());
                    sw.WriteLine(preferences.BottomOutofrangeProtectParameter1.ToString());
                    sw.WriteLine(preferences.BottomOutofrangeProtectParameter2.ToString());
                    sw.WriteLine(preferences.Presettime.ToString());
                    sw.WriteLine(preferences.SpareParameter1.ToString());
                    sw.WriteLine(preferences.SpareParameter2.ToString());
                    sw.WriteLine(preferences.ReturnLong.ToString());
                    sw.WriteLine(preferences.ReturnLat.ToString());
                    sw.Close();
                }


            }
            catch (Exception ee)
            {
                MessageBox.Show("输入有误，重新输入！");
            }
        }

        private void 退出ToolStripMenuItem1_Click(object sender, EventArgs e)
        {
            DialogResult btn=MessageBox.Show("是否退出系统？","系统退出确认",MessageBoxButtons.OKCancel);
            if (btn == DialogResult.OK)
            {
                UnregisterHotKey(Handle, 100);//卸载第1个快捷键
                UnregisterHotKey(Handle, 200);
                timer1.Stop();
                //thread_rec.Abort();
                //udp_send_recv.Close();
                this.Close();
            }
            else
            {
                ;
            }
        }
        // 打开扩展控制窗体（Form2），单实例复用。
        private void externToolStripMenuItem_Click(object sender, EventArgs e)
        {//扩展界面
            if (Form_extend == null)
            {
                Form_extend = new Form2(this);
                Form_extend.Visible = true;
                Form_extend.TopMost = true;
            }
            else
                Form_extend.WindowState = FormWindowState.Normal;
        }

        // 发送定时器（600ms）：
        // - 同步主界面按钮高亮
        // - 按协议填充 SEND[0..71]（含各字段缩放）
        // - 计算 SEND[69] 校验和
        // - 根据链路设置走 UDP 或无线电串口发送
        private void timer1_Tick(object sender, EventArgs e)
        {//定时器0.6s一次
            if (work_instruct == 0x01)
            {//任务开启已按下
                button2.BackColor = Color.SkyBlue;
            }
            else
            {
                button2.BackColor = Color.Transparent;
            }
            if (work_instruct == 0x02)
            {//任务取消已按下
                button3.BackColor = Color.SkyBlue;
            }
            else
            {
                button3.BackColor = Color.Transparent;
            }
            if (work_instruct == 0x91)
            {//清除故障已按下
                button37.BackColor = Color.SkyBlue;
            }
            else
            {
                button37.BackColor = Color.Transparent;
            }
            if (work_instruct == 0x92)
            {//初始化已按下
                button39.BackColor = Color.SkyBlue;
            }
            else
            {
                button39.BackColor = Color.Transparent;
            }
            if (work_instruct == 0x93)
            {//系统指令--备用指令1已按下
                button38.BackColor = Color.SkyBlue;
            }
            else
            {
                button38.BackColor = Color.Transparent;
            }
            if (work_instruct == 0x94)
            {//系统指令--备用指令2已按下
                button40.BackColor = Color.SkyBlue;
            }
            else
            {
                button40.BackColor = Color.Transparent;
            }

            ////////////////////无线电或者wifi发送--0.6秒1次///////////////////////////////////////////////////////////////////////////////////////////////////////////
            Byte checksum = 0;
            SEND[5] = frame;//发送帧序号
            SEND[6] = preferences.Objaddress;//目标地址
            SEND[7] = preferences.Workmode;//工作模式
            SEND[8] = (Byte)((preferences.DepthOutofrangeProtectParameter1 >> 8) & 0x00FF);//航行超深保护参数1
            SEND[9] = (Byte)(preferences.DepthOutofrangeProtectParameter1 & 0x00FF);//航行超深保护参数1
            SEND[10] = (Byte)((preferences.DepthOutofrangeProtectParameter2 >> 8) & 0x00FF);//航行超深保护参数2
            SEND[11] = (Byte)(preferences.DepthOutofrangeProtectParameter2 & 0x00FF);//航行超深保护参数2
            SEND[12] = (Byte)((preferences.BottomOutofrangeProtectParameter1 >> 8) & 0x00FF);//离底超限保护参数1
            SEND[13] = (Byte)(preferences.BottomOutofrangeProtectParameter1 & 0x00FF);//离底超限保护参数1
            SEND[14] = (Byte)((preferences.BottomOutofrangeProtectParameter2 >> 8) & 0x00FF);//离底超限保护参数2
            SEND[15] = (Byte)(preferences.BottomOutofrangeProtectParameter2 & 0x00FF);//离底超限保护参数2
            SEND[16] = (Byte)((preferences.Presettime >> 8) & 0x00FF);//预设时间
            SEND[17] = (Byte)(preferences.Presettime & 0x00FF);//预设时间
            SEND[18] = (Byte)((preferences.SpareParameter1 >> 8) & 0x00FF);//备用参数1
            SEND[19] = (Byte)(preferences.SpareParameter1 & 0x00FF);//备用参数1
            SEND[20] = (Byte)((preferences.SpareParameter2 >> 8) & 0x00FF);//备用参数2     -409左右  注意-2000到不了（-2000就是-20000，0xFF FF B1 E0）
            SEND[21] = (Byte)(preferences.SpareParameter2 & 0x00FF);//备用参数2
            SEND[22] = work_instruct;//工作指令
           
            SEND[23] = (Byte)((MotorSpeed1 >> 8) & 0x00FF);
            SEND[24] = (Byte)(MotorSpeed1 & 0x00FF);//电机转速1值下发赋值

            SEND[25] = (Byte)((MotorSpeed2 >> 8) & 0x00FF);
            SEND[26] = (Byte)(MotorSpeed2 & 0x00FF);//电机转速2值下发赋值

            SEND[27] = (Byte)((RudderAngle_LH >> 8) & 0x00FF);
            SEND[28] = (Byte)(RudderAngle_LH & 0x00FF);//左水平舵角值下发赋值

            SEND[29] = (Byte)((RudderAngle_RH >> 8) & 0x00FF);
            SEND[30] = (Byte)(RudderAngle_RH & 0x00FF);//右水平舵角值下发赋值

            SEND[31] = (Byte)((RudderAngle_UV >> 8) & 0x00FF);
            SEND[32] = (Byte)(RudderAngle_UV & 0x00FF);//上垂直舵

            SEND[33] = (Byte)((RudderAngle_LV >> 8) & 0x00FF);
            SEND[34] = (Byte)(RudderAngle_LV & 0x00FF);//下垂直舵

            SEND[35] = (Byte)((OrientationAngle >> 8) & 0x00FF);
            SEND[36] = (Byte)(OrientationAngle & 0x00FF);//定向角度

            SEND[37] = (Byte)((Parameter1 >>24) & 0x000000FF);
            SEND[38] = (Byte)((Parameter1 >> 16) & 0x000000FF);
            SEND[39] = (Byte)((Parameter1 >> 8) & 0x000000FF);
            SEND[40] = (Byte)(Parameter1 & 0x000000FF);//调参1

            SEND[41] = (Byte)((Parameter2 >> 24) & 0x000000FF);
            SEND[42] = (Byte)((Parameter2 >> 16) & 0x000000FF);
            SEND[43] = (Byte)((Parameter2 >> 8) & 0x000000FF);
            SEND[44] = (Byte)(Parameter2 & 0x000000FF);//调参2

            SEND[45] = (Byte)((Parameter3 >> 24) & 0x000000FF);
            SEND[46] = (Byte)((Parameter3 >> 16) & 0x000000FF);
            SEND[47] = (Byte)((Parameter3 >> 8) & 0x000000FF);
            SEND[48] = (Byte)(Parameter3 & 0x000000FF);//调参3

            SEND[49] = (Byte)((Parameter4 >> 24) & 0x000000FF);
            SEND[50] = (Byte)((Parameter4 >> 16) & 0x000000FF);
            SEND[51] = (Byte)((Parameter4 >> 8) & 0x000000FF);
            SEND[52] = (Byte)(Parameter4 & 0x000000FF);//调参4

            SEND[53] = (Byte)((Parameter5 >> 8) & 0x00FF);
            SEND[54] = (Byte)(Parameter5 & 0x00FF);//调参5

            SEND[55] = (Byte)((Parameter6 >> 8) & 0x00FF);
            SEND[56] = (Byte)(Parameter6 & 0x00FF);//调参6

            SEND[57] = (Byte)((Parameter7 >> 8) & 0x00FF);
            SEND[58] = (Byte)(Parameter7 & 0x00FF);//调参7

            SEND[59] = (Byte)((Parameter8 >> 8) & 0x00FF);
            SEND[60] = (Byte)(Parameter8 & 0x00FF);//调参8

            SEND[61] = (Byte)((Parameter9 >> 8) & 0x00FF);
            SEND[62] = (Byte)(Parameter9 & 0x00FF);//调参9

            SEND[63] = (Byte)((Parameter10 >> 8) & 0x00FF);
            SEND[64] = (Byte)(Parameter10 & 0x00FF);//调参10

            SEND[65] = (Byte)((Parameter11 >> 8) & 0x00FF);
            SEND[66] = (Byte)(Parameter11 & 0x00FF);//调参11

            SEND[67] = (Byte)((Parameter12 >> 8) & 0x00FF);
            SEND[68] = (Byte)(Parameter12 & 0x00FF);//调参12

            for (int ii = 0; ii <= 68; ii++)
                checksum += SEND[ii];
            SEND[69] = (Byte)(checksum & 0xFF);
            if (wiFiToolStripMenuItem.Checked == true && (!(preferences.Workmode == 0x00 || preferences.Workmode==0x04)))
            {//默认模式和回航模式不发送
                udp_send_recv.Send(SEND, SEND.Length, remoteipport);
            }
            else if (RadioToolStripMenuItem.Checked == true && (!(preferences.Workmode == 0x00 || preferences.Workmode == 0x04)))
            {//默认模式和回航模式不发送
                serialPort_Radio.Write(SEND, 0, SEND.Length);
            }
            frame++;
            if (frame == 0xFF)
                frame = 0;
            ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
        }

        private void button2_Click(object sender, EventArgs e)
        {//任务开启
            if (work_instruct != 0x01)
            {
                work_instruct = 0x01;
            }
            else 
            {
                work_instruct = 0x00;
            }

        }

        private void button3_Click(object sender, EventArgs e)
        {//任务取消
            if (work_instruct != 0x02)
            {
                work_instruct = 0x02;
            }
            else
            {
                work_instruct = 0x00;
            }
        }

        private void button37_Click(object sender, EventArgs e)
        {//清除故障
            if (work_instruct != 0x91)
            {
                work_instruct = 0x91;
            }
            else
            {
                work_instruct = 0x00;
            }
        }

        private void button39_Click(object sender, EventArgs e)
        {//初始化
            if (work_instruct != 0x92)
            {
                work_instruct = 0x92;
            }
            else
            {
                work_instruct = 0x00;
            }
        }

        private void button38_Click(object sender, EventArgs e)
        {//系统指令--备用指令1
            if (work_instruct != 0x93)
            {
                work_instruct = 0x93;
            }
            else
            {
                work_instruct = 0x00;
            }
        }

        private void button40_Click(object sender, EventArgs e)
        {//系统指令--备用指令2
            if (work_instruct != 0x94)
            {
                work_instruct = 0x94;
            }
            else
            {
                work_instruct = 0x00;
            }
        }

        // 北斗发送勾选逻辑：仅在自主定点/自主定向/回航模式下允许按 65s 周期发送。
        private void checkBox1_CheckedChanged(object sender, EventArgs e)
        {//北斗发送勾选改变
            if (checkBox1.Checked == true)
            {
                DialogResult btn = MessageBox.Show("确定勾选北斗发送？", "北斗发送确认", MessageBoxButtons.OKCancel);
                if (btn == DialogResult.OK)
                {
                    //timer定时65s发送一次----RS232
                    if (comboBox2.SelectedIndex >= 2 && comboBox2.SelectedIndex <= 4)//仅自主定点航行模式、自主定向航行模式和回航模式下，勾选北斗发送框后 65S 发送一次
                    {
                        flag_BDSEND = true;
                    }
                    else
                    {
                        flag_BDSEND = false;
                        cnt_65s = 0;
                        checkBox1.Checked = false;
                        MessageBox.Show("北斗发送仅在自主定点航行模式、自主定向航行模式和回航模式下有效！");
                    }
                }
                else
                {
                    checkBox1.Checked = false;
                    flag_BDSEND = false;
                    cnt_65s = 0;
                }
            }
            else
            {
                flag_BDSEND = false;
                cnt_65s = 0;
            }
        }

        // WiFi 模式切换：开启/关闭 WiFi 接收线程，同时互斥关闭无线电串口。
        private void wiFiToolStripMenuItem_Click(object sender, EventArgs e)
        {//wifi
            if (wiFiToolStripMenuItem.Checked == true)
            {
                thread_rec.Abort();//关闭wifi接收线程
                wiFiToolStripMenuItem.Checked = false;
            }
            else
            {
                thread_rec = new Thread(THREAD_REC);
                thread_rec.Start();//开启wifi接收线程
                wiFiToolStripMenuItem.Checked = true;
                
                RadioToolStripMenuItem.Checked = false;
                serialPort_Radio.Close();//同时关闭无线电
            }
        }

        // 无线电模式切换：开启/关闭无线电串口，同时互斥关闭 WiFi 接收线程。
        private void RadioToolStripMenuItem_Click(object sender, EventArgs e)
        {//无线电
            if (RadioToolStripMenuItem.Checked == true)
            {
                RadioToolStripMenuItem.Checked = false;
                serialPort_Radio.Close();//关闭无线电串口
            }
            else
            {
                serialPort_Radio.Open();//打开无线电 同时关闭wifi接收
                RadioToolStripMenuItem.Checked = true;

                thread_rec.Abort();//关闭wifi接收线程
                wiFiToolStripMenuItem.Checked = false;
            }
        }
        List<Byte> buffer_radio = new List<Byte>(2048);
        bool Head_flag = false;
        UInt16 cscs = 0;
        // 无线电串口接收：
        // - 先拼接缓冲，再找帧头
        // - 满 145 字节后做帧尾和校验
        // - 通过后置 ComMode=1 并调用 display()
        private void serialPort_Radio_DataReceived(object sender, System.IO.Ports.SerialDataReceivedEventArgs e)
        {//无线电接收
            int n=serialPort_Radio.BytesToRead;
            if (n > 0)
            {
                Byte[] recv = new Byte[n];
                serialPort_Radio.Read(recv, 0, n);
                buffer_radio.AddRange(recv);
                if (buffer_radio.Count > 145 * 5)//当缓存区数据大于5帧数据时，清空
                {
                    buffer_radio.Clear();
                }
            }
            //RECEV[0] == 0x24 && RECEV[1] == 0x41 && RECEV[2] == 0x55 && RECEV[3] == 0x56 && RECEV[4] == 0x91 && RECEV[143] == 0xFF && RECEV[144] == 0xFF
            if (buffer_radio.Count > 5 && Head_flag == false)//找头
            {
                for (int ii = 0; ii < (buffer_radio.Count - 4); ii++)
                {
                    if (buffer_radio[ii] == 0x24 && buffer_radio[ii + 1] == 0x41 && buffer_radio[ii + 2] == 0x55 && buffer_radio[ii + 3] == 0x56 && buffer_radio[ii + 4] == 0x91)
                    {
                        Head_flag = true;
                        buffer_radio.RemoveRange(0, ii);//移除帧头前面的部分
                        break;
                    }
                }
            }
            if (buffer_radio.Count >= 145 && Head_flag == true)//找尾 一帧数据145字节
            {
                if (buffer_radio[0] == 0x24 && buffer_radio[1] == 0x41 && buffer_radio[2] == 0x55 && buffer_radio[3] == 0x56 && buffer_radio[4] == 0x91 && buffer_radio[143] == 0xFF && buffer_radio[144] == 0xFF)
                {
                    Byte checksum = 0;
                    for (int m = 0; m < 142; m++)
                        checksum += buffer_radio[m];
                    if (buffer_radio[142] == (checksum & 0xFF))//校验正确
                    {
                        RECEV = new Byte[145];
                        for (int mm = 0; mm < 145; mm++)
                            RECEV[mm] = buffer_radio[mm];
                        buffer_radio.RemoveRange(0, 145);
                        Head_flag = false;
                        ComMode = 1;//无线电串口接收
                        display();
                    }
                    else
                    {//校验不对
                        buffer_radio.RemoveRange(0, 145);
                        Head_flag = false;
                    }
                }
                else
                {
                    buffer_radio.RemoveRange(0, 145);
                    Head_flag = false;
                }
            }
        }

        // 将两个 ASCII 十六进制字符合并为 1 个字节（例如 'A','8' -> 0xA8）。
        private byte addxxj(byte A, byte B)
        {
            byte a = 0;
            byte b = 0;
            if (A >= '0' && A <= '9') { a = (byte)(A - '0'); }
            else if (A >= 'A' && A <= 'F') { a = (byte)(A - 'A' + 10); }
            else if (A >= 'a' && A <= 'f') { a = (byte)(A - 'a' + 10); }

            if (B >= '0' && B <= '9') { b = (byte)(B - '0'); }
            else if (B >= 'A' && B <= 'F') { b = (byte)(B - 'A' + 10); }
            else if (B >= 'a' && B <= 'f') { b = (byte)(B - 'a' + 10); }

            return (byte)((a << 4) + b);
        }


        List<Byte> buffer_BD_pre = new List<Byte>(2048);//包含$BDTXR的北斗数据帧
        //List<Byte> buffer_BD = new List<Byte>(2048);//去掉$BDTXR的北斗数据帧
        bool Head_flag_BD = false;
        // 北斗串口接收：从 $BDTXR...\r\n 文本帧中提取载荷，做 XOR 校验，
        // 再将 ASCII 十六进制转换为二进制 72 字节帧并进一步校验。
        private void serialPort_BD_DataReceived(object sender, System.IO.Ports.SerialDataReceivedEventArgs e)
        {//北斗数据接收--72字节
         //最新北斗接收的数据--169字节
            int n = serialPort_BD.BytesToRead;
            if (n > 0)
            {
                Byte[] recv = new Byte[n];
                serialPort_BD.Read(recv, 0, n);
                buffer_BD_pre.AddRange(recv);
                if (buffer_BD_pre.Count > 169 * 5)//当缓存区数据大于5帧数据时，清空
                {
                    buffer_BD_pre.Clear();
                }
            }
            if (buffer_BD_pre.Count > 22 && Head_flag_BD == false)//找头
            {
                for (int ii = 0; ii < (buffer_BD_pre.Count - 22); ii++) //$BDTXR,1,1234567,2,,A4共22个字节
                {
                    if (buffer_BD_pre[ii] == '$' && buffer_BD_pre[ii + 1] == 'B' && buffer_BD_pre[ii + 2] == 'D' && buffer_BD_pre[ii + 3] == 'T' && buffer_BD_pre[ii + 4] == 'X' && buffer_BD_pre[ii + 5] == 'R')
                    {
                        Head_flag_BD = true;
                        buffer_BD_pre.RemoveRange(0, ii);//移除帧头前面的部分
                        break;
                    }
                }
                //for (int kk = 22; kk < (buffer_BD_pre.Count - 3); kk+=2) ////将两个ASCII码合并成1个hex码，从buffer_BD[22]到buffer_BD[93]
                //{
                //    //例如：将字符'2','4'   合并成16进制 0x24

                //}
            }
            if (Head_flag_BD == true && buffer_BD_pre.Count>22)//头找到了再找尾，0x0D 0x0A结尾
            {
                for (int ii = 0; ii < buffer_BD_pre.Count - 1; ii++)
                {
                    if (buffer_BD_pre[ii] == 0x0D && buffer_BD_pre[ii + 1] == 0x0A)//
                    {
                        int frame_tail = ii;
                        Byte XOR_check=buffer_BD_pre[1];
                        //算校验
                        for(int jj=2;jj<frame_tail-3;jj++)
                            XOR_check = (Byte)(XOR_check ^ buffer_BD_pre[jj]);
                        if (buffer_BD_pre[frame_tail - 3] == '*' && XOR_check == addxxj(buffer_BD_pre[frame_tail - 2], buffer_BD_pre[frame_tail - 1]))
                        {//校验正确
                            if(buffer_BD_pre[9]=='0'&& buffer_BD_pre[10]=='9'&&buffer_BD_pre[11]=='8'&&buffer_BD_pre[12]=='9'&&buffer_BD_pre[13]=='5'&&buffer_BD_pre[14]=='6'&&buffer_BD_pre[15]=='5')
                            {//0989565发来的数据 解析
                                if ((frame_tail - 25) == 72 * 2)//从22字节开始frame_tail - 4 - 22+1
                                {//完整一包数据
                                    RECEV_BD = new Byte[72];
                                    for (int mm = 0; mm < 72; mm++)
                                    {
                                        RECEV_BD[mm] = addxxj(buffer_BD_pre[mm * 2 + 22], buffer_BD_pre[mm * 2 + 23]);
                                        if (RECEV_BD[0] == 0x24 && RECEV_BD[1] == 0x41 && RECEV_BD[2] == 0x55 && RECEV_BD[3] == 0x56 && RECEV_BD[4] == 0x48 && RECEV_BD[70] == 0xFF && RECEV_BD[71] == 0xFF)
                                        {
                                            Byte checksum = 0;
                                            for (int m = 0; m < 69; m++)
                                                checksum += RECEV_BD[m];
                                            if (RECEV_BD[69] == (checksum & 0xFF))//校验正确
                                            {
                                                ComMode = 3;//北斗串口接收
                                                display_BD();
                                            }
                                            else
                                            {//校验错误 
                                                ;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        else
                        {//校验错误或者没找到*
                            ;
                        }
                        buffer_BD_pre.RemoveRange(0, frame_tail + 2);
                        Head_flag_BD = false;
                    }
                }
            }
            //if (buffer_BD.Count >= 72 && Head_flag_BD == true)//找尾 一帧数据72字节
            //{
            //    if (buffer_BD[0] == 0x24 && buffer_BD[1] == 0x41 && buffer_BD[2] == 0x55 && buffer_BD[3] == 0x56 && buffer_BD[4] == 0x48 && buffer_BD[70] == 0xFF && buffer_BD[71] == 0xFF)
            //    {
            //        Byte checksum = 0;
            //        for (int m = 0; m < 69; m++)
            //            checksum += buffer_BD[m];
            //        if (buffer_BD[69] == (checksum & 0xFF))//校验正确
            //        {
            //            RECEV_BD = new Byte[72];
            //            for (int mm = 0; mm < 72; mm++)
            //                RECEV_BD[mm] = buffer_BD[mm];
            //            buffer_BD.RemoveRange(0, 72);
            //            Head_flag_BD = false;
            //            ComMode = 3;//北斗串口接收
            //            display_BD();
            //        }
            //        else
            //        {//校验错误
            //            buffer_BD.RemoveRange(0, 72);
            //            Head_flag_BD = false;
            //        }
            //    }
            //    else
            //    {
            //        buffer_BD.RemoveRange(0, 72);
            //        Head_flag_BD = false;
            //    }
            //}
        }

        // 允许拖拽无边框窗体移动。
        private void Form1_MouseDown(object sender, MouseEventArgs e)
        {
            //拖动窗体
            this.Cursor = System.Windows.Forms.Cursors.SizeAll;
            ReleaseCapture();
            SendMessage(this.Handle, WM_SYSCOMMAND, SC_MOVE + HTCAPYION, 0);
            this.Cursor = System.Windows.Forms.Cursors.Default;
        }

        // 北斗发送定时器：勾选后按 65s 节奏组 34 字节压缩包，通过 CCTXA 封装后串口发送。
        // 北斗分支仅允许 0x00/0x01/0x02/0x91/0x92 指令透传。
        private void timer2_Tick(object sender, EventArgs e)
        {
            /***************************************************************北斗----若勾选65s发送一次******************************************************************/
            if (flag_BDSEND == true)
            {
                cnt_65s++;
                if (cnt_65s == 65)
                {
                    cnt_65s = 0;                    //发送
                    SEND_BD[5] = frame_BD;//报文序号
                    SEND_BD[6] = preferences.Objaddress;//目标地址
                    SEND_BD[7] = preferences.Workmode;//工作模式
                    SEND_BD[8] = (Byte)((preferences.DepthOutofrangeProtectParameter1 >> 8) & 0x00FF);//航行超深保护参数1
                    SEND_BD[9] = (Byte)(preferences.DepthOutofrangeProtectParameter1 & 0x00FF);//航行超深保护参数1
                    SEND_BD[10] = (Byte)((preferences.DepthOutofrangeProtectParameter2 >> 8) & 0x00FF);//航行超深保护参数2
                    SEND_BD[11] = (Byte)(preferences.DepthOutofrangeProtectParameter2 & 0x00FF);//航行超深保护参数2
                    SEND_BD[12] = (Byte)((preferences.BottomOutofrangeProtectParameter1 >> 8) & 0x00FF);//离底超限保护参数1
                    SEND_BD[13] = (Byte)(preferences.BottomOutofrangeProtectParameter1 & 0x00FF);//离底超限保护参数1
                    SEND_BD[14] = (Byte)((preferences.BottomOutofrangeProtectParameter2 >> 8) & 0x00FF);//离底超限保护参数2
                    SEND_BD[15] = (Byte)(preferences.BottomOutofrangeProtectParameter2 & 0x00FF);//离底超限保护参数2
                    SEND_BD[16] = (Byte)((preferences.Presettime >> 8) & 0x00FF);//预设时间
                    SEND_BD[17] = (Byte)(preferences.Presettime & 0x00FF);//预设时间
                    SEND_BD[18] = (Byte)((preferences.SpareParameter1 >> 8) & 0x00FF);//备用参数1
                    SEND_BD[19] = (Byte)(preferences.SpareParameter1 & 0x00FF);//备用参数1
                    SEND_BD[20] = (Byte)((preferences.SpareParameter2 >> 8) & 0x00FF);//备用参数2     -409左右  注意-2000到不了（-2000就是-20000，0xFF FF B1 E0）
                    SEND_BD[21] = (Byte)(preferences.SpareParameter2 & 0x00FF);//备用参数2
                    /*1、 0X00 默认无含义      2、 0X01 任务开启      3、 0X02 任务取消        4、 0X91 清除故障          5、 0X92 初始化*/
                    if (work_instruct == 0x00 || work_instruct == 0x01 || work_instruct == 0x02 || work_instruct == 0x91 || work_instruct == 0x92)
                    {
                        SEND_BD[22] = work_instruct;
                    }
                    //23-26
                    SEND_BD[23] = (Byte)((preferences.ReturnLong >> 24) & 0x000000FF);
                    SEND_BD[24] = (Byte)((preferences.ReturnLong >> 16) & 0x000000FF);
                    SEND_BD[25] = (Byte)((preferences.ReturnLong >> 8) & 0x000000FF);
                    SEND_BD[26] = (Byte)(preferences.ReturnLong & 0x000000FF);
                    //27-30
                    SEND_BD[27] = (Byte)((preferences.ReturnLat >> 24) & 0x000000FF);
                    SEND_BD[28] = (Byte)((preferences.ReturnLat >> 16) & 0x000000FF);
                    SEND_BD[29] = (Byte)((preferences.ReturnLat >> 8) & 0x000000FF);
                    SEND_BD[30] = (Byte)(preferences.ReturnLat & 0x000000FF);

                    Byte checksum_BD = 0;
                    for (int ii = 0; ii <= 30; ii++)
                        checksum_BD += SEND_BD[ii];
                    SEND_BD[31] = (Byte)(checksum_BD & 0xFF);
                    //serialPort_BD.Write(SEND_BD, 0, 34);
                    CCTXA(Dest_ICnum_gd, SEND_BD, 34);
                    frame_BD++;
                    if (frame_BD == 0xFF)
                        frame_BD = 0;
                }
            }
            /**********************************************************************************************************************************************************/
        }

        // 地图刷新定时器：触发 pictureBox 重绘。
        private void timer3_Tick(object sender, EventArgs e)
        {//绘图
            pictureBox1.Invalidate();
        }
        // 鼠标滚轮缩放地图比例尺 picM（带上下限保护）。
        private void pictureBox1_MouseWheel(Object sender, MouseEventArgs e)//鼠标动作
        {
            int numberoftextlinestomove = e.Delta * SystemInformation.MouseWheelScrollLines / 120;//获取滚动鼠标轮时所滚动过的行数
            if (numberoftextlinestomove > 0)
            {
                picM = picM / 0.9F;
                if (picM > 12)
                    picM = 12;
            }
            else
            {
                picM = picM * 0.9F;
                if (picM < 0.001)
                    picM = 0.001F;
            }
            pictureBox1.Invalidate();
        }
        float MapOriginLineW=0.0F;
        float MapOriginLineL=0.0F;
        // 地图绘制入口：网格、航行器姿态、GPS轨迹、航位推算轨迹、测距线与自主定点航路。
        private void pictureBox1_Paint(object sender, PaintEventArgs e)
        {
            MapOriginLineW = pictureBox1.Width / 2.0f;//宽
            MapOriginLineL = pictureBox1.Height / 2.0f;//长
            float MapLineLower = (MapOriginLineW <= MapOriginLineL ? MapOriginLineW : MapOriginLineL);
            float Ratio = MapLineLower / 225.0F;//比例
            float pi = (float)Math.PI / 180.0F;
            PointF newpointF2 = new PointF();

            Graphics picGraphics = e.Graphics;
            Pen mypen = new Pen(Color.CadetBlue, 0.5F);//画笔设置
            SolidBrush drawbrush = new SolidBrush(Color.Green);//笔颜色
            picGraphics.SmoothingMode = SmoothingMode.AntiAlias;//线条设置
            picGraphics.TranslateTransform(MapOriginLineW, MapOriginLineL);//坐标原点

            mypen.DashStyle = DashStyle.Solid;
            //用设置好的笔画线
            picGraphics.DrawLine(mypen, 0, -MapOriginLineL, 0, MapOriginLineL);
            picGraphics.DrawLine(mypen, -MapOriginLineW, 0, MapOriginLineW, 0);

            mypen.DashStyle = DashStyle.DashDot;
            for (int i = 1; i < 9; i++)
            {
                if (100 * i < MapOriginLineW)
                {
                    picGraphics.DrawLine(mypen, -100 * i, -MapOriginLineL, -100 * i, MapOriginLineL);
                    picGraphics.DrawLine(mypen, 100 * i, -MapOriginLineL, 100 * i, MapOriginLineL);
                }
                if (!(100 * i < MapOriginLineL))
                    continue;
                picGraphics.DrawLine(mypen, -MapOriginLineW, 100 * i, MapOriginLineW, 100 * i);
                picGraphics.DrawLine(mypen, -MapOriginLineW, -100 * i, MapOriginLineW, -100 * i);
            }

            Font drawFont = new Font("Arial", 8 * Ratio);
            SolidBrush drawBrush = new SolidBrush(Color.NavajoWhite);
            string drawstring = "航行器";
            PointF drawPoint = new PointF(MapOriginLineW - 65 * Ratio, -MapOriginLineL + 18 * Ratio);
            picGraphics.DrawString(drawstring, drawFont, drawBrush, drawPoint);

            PointF[] pointsAUV =
            {
                new PointF(MapOriginLineW-20*Ratio,-MapOriginLineL+5*Ratio),
                new PointF(MapOriginLineW-25*Ratio,-MapOriginLineL+10*Ratio),
                new PointF(MapOriginLineW-25*Ratio,-MapOriginLineL+30*Ratio),
                new PointF(MapOriginLineW-15*Ratio,-MapOriginLineL+30*Ratio),
                new PointF(MapOriginLineW-15*Ratio,-MapOriginLineL+10*Ratio),
                new PointF(MapOriginLineW-20*Ratio,-MapOriginLineL+5*Ratio)
            };
            picGraphics.DrawLines(new Pen(Color.CornflowerBlue,2.0F*Ratio),pointsAUV);
            picGraphics.FillEllipse(new SolidBrush(Color.CornflowerBlue),MapOriginLineW-22*Ratio,-MapOriginLineL+18*Ratio,4*Ratio,4*Ratio);

            //比例
            picGraphics.DrawString("量程："+((100/picM).ToString("F0"))+"米/格",drawFont,drawBrush,new PointF(-MapOriginLineW,-MapOriginLineL+23*Ratio));


            newpointF2.X = (float)(LONG_AUV - MapOriginLon) * 111120.0F * (float)Math.Cos(MapOriginLat * Math.PI / 180.0F);
            newpointF2.Y = (float)(LAT_AUV - MapOriginLat) * 111120F;
            //画动态潜航体
            PointF[] AUVPoints =
                {
                new PointF(newpointF2.X*picM + Ratio*15*(float) Math.Sin(CourseAngle_AUV*pi),-newpointF2.Y*picM - Ratio*15*(float) Math.Cos(CourseAngle_AUV*pi)),
                new PointF(newpointF2.X*picM + Ratio*11.18F*(float) Math.Sin((CourseAngle_AUV + 30)*pi),-newpointF2.Y*picM - Ratio*11.18F*(float) Math.Cos((CourseAngle_AUV + 30)*pi)),
                new PointF(newpointF2.X*picM + Ratio*11.18F*(float) Math.Sin((CourseAngle_AUV + 150)*pi),-newpointF2.Y*picM - Ratio*11.18F*(float) Math.Cos((CourseAngle_AUV + 150)*pi)),
                new PointF(newpointF2.X*picM + Ratio*11.18F*(float) Math.Sin((CourseAngle_AUV + 210)*pi),-newpointF2.Y*picM - Ratio*11.18F*(float) Math.Cos((CourseAngle_AUV + 210)*pi)),
                new PointF(newpointF2.X*picM + Ratio*11.18F*(float) Math.Sin((CourseAngle_AUV + 330)*pi),-newpointF2.Y*picM - Ratio*11.18F*(float) Math.Cos((CourseAngle_AUV + 330)*pi)),
                new PointF(newpointF2.X*picM + Ratio*15*(float) Math.Sin(CourseAngle_AUV*pi),-newpointF2.Y*picM - Ratio*15*(float) Math.Cos(CourseAngle_AUV*pi))
                };
            picGraphics.DrawLines(new Pen(Color.CornflowerBlue, 2.0F * Ratio), AUVPoints);
            picGraphics.FillEllipse(new SolidBrush(Color.CornflowerBlue), -2.0F * Ratio + newpointF2.X * picM, -2.0F * Ratio - newpointF2.Y * picM, 4 * Ratio, 4 * Ratio);

            
            //航位推算轨迹
            if (Queue_GPS_CALC.Count > 1)
            {
                IEnumerator<PointF> myEnumerator1 = Queue_GPS_CALC.GetEnumerator();
                while (myEnumerator1.MoveNext())
                {
                    PointF newpointF1 = myEnumerator1.Current;
                    newpointF2.X = (float)(newpointF1.X - MapOriginLon) * 111120.0F * (float)Math.Cos(MapOriginLat * Math.PI / 180.0F);
                    newpointF2.Y = (float)(newpointF1.Y - MapOriginLat) * 111120.0F;
                    mypen.Color = Color.White;
                    picGraphics.DrawArc(new Pen(Color.White), (float)newpointF2.X * picM, (float)-newpointF2.Y * picM, 2.0F, 2.0F, 0.0F, 360.0F);
                }
            }
            //GPS轨迹
            if (Queue_GPS.Count > 1)
            {
                IEnumerator<PointF> myEnumerator = Queue_GPS.GetEnumerator();
                while (myEnumerator.MoveNext())
                {
                    PointF newpointF = myEnumerator.Current;
                    newpointF2.X = (float)(newpointF.X - MapOriginLon) * 111120.0F * (float)Math.Cos(MapOriginLat * Math.PI / 180.0F);
                    newpointF2.Y = (float)(newpointF.Y - MapOriginLat) * 111120.0F;
                    mypen.Color = Color.Red;
                    picGraphics.DrawArc(new Pen(Color.Red), (float)newpointF2.X * picM, (float)-newpointF2.Y * picM, 2.0F, 2.0F, 0.0F, 360.0F);
                }
            }
            //画出测距线
            if (flag_distance) //画出测距线
            {
                picGraphics.DrawLine(new Pen(Color.Yellow, 2.0F), (Int32)ruleStartPosition.X, (Int32)ruleStartPosition.Y, (Int32)ruleEndPosition.X, (Int32)ruleEndPosition.Y);

                double distancex, distancey, distance, angle;
                distancex = ruleEndPosition.X - ruleStartPosition.X;//拖动的距离
                distancey = ruleEndPosition.Y - ruleStartPosition.Y;

                distance = Math.Sqrt(distancex * distancex + distancey * distancey);
                angle = Math.Atan2(distancey, distancex) * 180 / Math.PI;
                distance = distance / picM;

                double couA = angle;//角度

                couA += 90;
                if (couA < 0)
                {
                    couA += 360;
                }
                picGraphics.DrawString(distance.ToString("F0") + @"米，" + couA.ToString("F1") + @"°", new Font("Times New Roman", 12), Brushes.Yellow, (float)ruleEndPosition.X, (float)ruleEndPosition.Y - 15);
            }

            //画出自主定点规划航路
            double Route_Lon1, Route_Lat1, Route_Lon2, Route_Lat2;
            PointF newPointF2 = new PointF();
            PointF newPointF3 = new PointF();
            if (Autofixedpoint.Count > 0)
            {
                if (Autofixedpoint.Count == 1)
                {
                    Route_Lon1 = Autofixedpoint[0].Longitude; //经度
                    Route_Lat1 = Autofixedpoint[0].Lat; //纬度
                    newPointF2.X = (float)((Route_Lon1 - MapOriginLon) * 111120.0f * (float)Math.Cos(MapOriginLat * Math.PI / 180.0f));
                    newPointF2.Y = -(float)(Route_Lat1 - MapOriginLat) * 111120.0f;
                    //画出节点
                    picGraphics.FillEllipse(Brushes.Red, newPointF2.X * picM - 2, newPointF2.Y * picM - 2, 4.0f, 4.0f);
                    string str = ("0_" + Autofixedpoint[0].Longitude.ToString("F6") + "_" + Autofixedpoint[0].Lat.ToString("F6") + "_" + Autofixedpoint[0].Control_Strategy.ToString() + "_" + Autofixedpoint[0].Control_Param.ToString() + "_" + Autofixedpoint[0].Motor_Speed.ToString() + "_" + Convert.ToString(Autofixedpoint[0].Device_Control,2).PadLeft(8, '0').ToString());//Convert.ToString(Autofixedpoint[i].Device_Control,2).PadLeft(8,'0').ToString()
                    picGraphics.DrawString(str, drawFont, Brushes.Red, new PointF(newPointF2.X * picM, newPointF2.Y * picM));
                }
                else
                {
                    for (int i = 1; i < Autofixedpoint.Count; i++)
                    {
                        Route_Lon1 = Autofixedpoint[i - 1].Longitude; //经度
                        Route_Lat1 = Autofixedpoint[i - 1].Lat; //纬度
                        Route_Lon2 = Autofixedpoint[i].Longitude;
                        Route_Lat2 = Autofixedpoint[i].Lat;

                        newPointF2.X = (float)((Route_Lon1 - MapOriginLon) * 111120.0f * (float)Math.Cos(MapOriginLat * Math.PI / 180.0f));
                        newPointF2.Y = -(float)(Route_Lat1 - MapOriginLat) * 111120.0f;
                        newPointF3.X = (float)((Route_Lon2 - MapOriginLon) * 111120.0f * (float)Math.Cos(MapOriginLat * Math.PI / 180.0f));
                        newPointF3.Y = -(float)(Route_Lat2 - MapOriginLat) * 111120.0f;

                        //画出两点间的直线
                        picGraphics.DrawLine(new Pen(Color.LimeGreen, 2.0F), newPointF2.X * picM, newPointF2.Y * picM, newPointF3.X * picM, newPointF3.Y * picM);
                        //if (newPointF3.X >= newPointF2.X && newPointF3.Y <= newPointF2.Y)
                        //    picGraphics.DrawString((Math.Atan((newPointF3.X - newPointF2.X) / (newPointF2.Y - newPointF3.Y)) * 180 / Math.PI).ToString("0.0") + "°" + "\r\n" + (Math.Sqrt(Math.Pow((newPointF3.X - newPointF2.X), 2) + Math.Pow((newPointF3.Y - newPointF2.Y), 2))).ToString("0.0") + "m", drawFont, Brushes.Red, new PointF((newPointF2.X + (newPointF3.X - newPointF2.X) / 2.0f) * picM, (newPointF2.Y + (newPointF3.Y - newPointF2.Y) / 2.0f) * picM));
                        //else if (newPointF3.X >= newPointF2.X && newPointF3.Y > newPointF2.Y)
                        //    picGraphics.DrawString((Math.Atan((newPointF3.X - newPointF2.X) / (newPointF2.Y - newPointF3.Y)) * 180 / Math.PI + 180).ToString("0.0") + "°" + "\r\n" + (Math.Sqrt(Math.Pow((newPointF3.X - newPointF2.X), 2) + Math.Pow((newPointF3.Y - newPointF2.Y), 2))).ToString("0.0") + "m", drawFont, Brushes.Red, new PointF((newPointF2.X + (newPointF3.X - newPointF2.X) / 2.0f) * picM, (newPointF2.Y + (newPointF3.Y - newPointF2.Y) / 2.0f) * picM));
                        //else if (newPointF3.X < newPointF2.X && newPointF3.Y > newPointF2.Y)
                        //    picGraphics.DrawString((Math.Atan((newPointF3.X - newPointF2.X) / (newPointF2.Y - newPointF3.Y)) * 180 / Math.PI + 180).ToString("0.0") + "°" + "\r\n" + (Math.Sqrt(Math.Pow((newPointF3.X - newPointF2.X), 2) + Math.Pow((newPointF3.Y - newPointF2.Y), 2))).ToString("0.0") + "m", drawFont, Brushes.Red, new PointF((newPointF2.X + (newPointF3.X - newPointF2.X) / 2.0f) * picM, (newPointF2.Y + (newPointF3.Y - newPointF2.Y) / 2.0f) * picM));
                        //else
                        //    picGraphics.DrawString((Math.Atan((newPointF3.X - newPointF2.X) / (newPointF2.Y - newPointF3.Y)) * 180 / Math.PI + 360).ToString("0.0") + "°" + "\r\n" + (Math.Sqrt(Math.Pow((newPointF3.X - newPointF2.X), 2) + Math.Pow((newPointF3.Y - newPointF2.Y), 2))).ToString("0.0") + "m", drawFont, Brushes.Red, new PointF((newPointF2.X + (newPointF3.X - newPointF2.X) / 2.0f) * picM, (newPointF2.Y + (newPointF3.Y - newPointF2.Y) / 2.0f) * picM));
                        //画出节点
                        picGraphics.FillEllipse(Brushes.Red, newPointF2.X * picM - 2, newPointF2.Y * picM - 2, 4.0f, 4.0f);
                        picGraphics.FillEllipse(Brushes.Red, newPointF3.X * picM - 2, newPointF3.Y * picM - 2, 4.0f, 4.0f);
                        string str1 = ((i - 1).ToString() + "_" + Autofixedpoint[i - 1].Longitude.ToString("F6") + "_" + Autofixedpoint[i - 1].Lat.ToString("F6") + "_" + Autofixedpoint[i - 1].Control_Strategy.ToString() + "_" + Autofixedpoint[i - 1].Control_Param.ToString() + "_" + Autofixedpoint[i - 1].Motor_Speed.ToString() + "_" + Convert.ToString(Autofixedpoint[i - 1].Device_Control,2).PadLeft(8, '0'));
                        string str2 = (i.ToString() + "_" + Autofixedpoint[i].Longitude.ToString("F6") + "_" + Autofixedpoint[i].Lat.ToString("F6") + "_" + Autofixedpoint[i].Control_Strategy.ToString() + "_" + Autofixedpoint[i].Control_Param.ToString() + "_" + Autofixedpoint[i].Motor_Speed.ToString() + "_" + Convert.ToString(Autofixedpoint[i].Device_Control,2).PadLeft(8, '0'));
                        picGraphics.DrawString(str1, drawFont, Brushes.Red, new PointF(newPointF2.X * picM, newPointF2.Y * picM));
                        picGraphics.DrawString(str2, drawFont, Brushes.Red, new PointF(newPointF3.X * picM, newPointF3.Y * picM));
                        //if (Autofixedpoint.Count == i)
                        //{
                        //    picGraphics.DrawString((i).ToString(), drawFont, drawBrushYellow, new PointF(newPointF2.X * picM, newPointF2.Y * picM));
                        //    if (i == (Autofixedpoint.Count - 1))
                        //    {
                        //        picGraphics.DrawString((i + 1).ToString(), drawFont, drawBrushYellow, new PointF(newPointF3.X * picM, newPointF3.Y * picM));
                        //    }
                        //}
                    }
                }
            }
        }
        bool mouseRightDragdownFlag = false;
        PointF mouseMoveStart = new PointF();
        // 地图鼠标按下：
        // - 右键：进入平移或测距起点
        // - 左键：在“自主定点选点模式”下添加航点并写入表格
        private void pictureBox1_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right)
            {
                if (flag_distance == false)
                {
                    mouseRightDragdownFlag = true;//右键按下拖动标志置为true
                    mouseMoveStart.X = e.X;
                    mouseMoveStart.Y = e.Y;
                }
                else
                {
                    ruleStartPosition = new PointF();
                    ruleStartPosition.X = e.X - MapOriginLineW;
                    ruleStartPosition.Y = e.Y - MapOriginLineL;
                }
            }
            if (e.Button == MouseButtons.Left)
            {
                if (flag_autofixedpoint)
                {//自主定点选点
                    double myX = (double)(((e.X - MapOriginLineW) / picM) / (111120.0f * Math.Cos(MapOriginLat * Math.PI / 180.0f)) + MapOriginLon);
                    double myY = (double)(((MapOriginLineL - e.Y) / picM) / 111120.0f + MapOriginLat);

                    AutoFixedPoint newAutoFixedPoint;
                    newAutoFixedPoint.Longitude = myX;
                    newAutoFixedPoint.Lat = myY;
                    newAutoFixedPoint.Control_Strategy = 0;
                    newAutoFixedPoint.Control_Param = 0.0F;
                    newAutoFixedPoint.Motor_Speed = 0;
                    newAutoFixedPoint.Device_Control = 0;
                    Autofixedpoint.Add(newAutoFixedPoint);
                    DataGridViewRowCollection addrows = dataGridView1.Rows;
                    String[] rows = { 
                                            autofixedpointNUM.ToString(), 
                                            newAutoFixedPoint.Longitude.ToString("F6"), 
                                            newAutoFixedPoint.Lat.ToString("F6"), 
                                            newAutoFixedPoint.Control_Strategy == 0?"定深":"定高",
                                            newAutoFixedPoint.Control_Param.ToString("F1"), 
                                            newAutoFixedPoint.Motor_Speed.ToString(), 
                                            newAutoFixedPoint.Device_Control.ToString()};
                    addrows.Add(rows);
                    autofixedpointNUM++;
                }
            }
        }

        // 地图鼠标抬起：结束右键拖拽/测距状态。
        private void pictureBox1_MouseUp(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right)
            {
                mouseRightDragdownFlag = false;//右键弹起置为false
                pictureBox1.Cursor = Cursors.Default;
                flag_distance = false;
                ruleEndPosition = new PointF();
                ruleStartPosition = new PointF();
            }
        }

        // 地图鼠标移动：实时显示经纬度；右键拖拽平移地图；测距模式动态更新终点。
        private void pictureBox1_MouseMove(object sender, MouseEventArgs e)
        {
            double MouseLon = (double)(((e.X - MapOriginLineW) / picM) / (111120.0f * Math.Cos(MapOriginLat * Math.PI / 180.0f)) + MapOriginLon);
            double MouseLat = (double)((MapOriginLineL - e.Y) / picM) / 111120.0f + (float)MapOriginLat;
            toolStripStatusLabel2.Text = ("鼠标:" + MouseLon.ToString("F6") + "°," + MouseLat.ToString("F6") + "°");

            if (mouseRightDragdownFlag && e.Button == MouseButtons.Right)
            {//拖拽 移动
                pictureBox1.Cursor = Cursors.SizeAll;

                float xoff = e.X - mouseMoveStart.X;
                float yoff = e.Y - mouseMoveStart.Y;

                float OriginLONG_off = (xoff / picM) / 111120 * (float)Math.Cos(MapOriginLat * Math.PI / 180.0F);
                float OriginLAT_off = (yoff / picM) / 111120;

                MapOriginLon = MapOriginLon - OriginLONG_off;
                MapOriginLat = MapOriginLat + OriginLAT_off;

                mouseMoveStart.X = e.X;
                mouseMoveStart.Y = e.Y;
                pictureBox1.Invalidate();
            }
            if (flag_distance == true && e.Button == MouseButtons.Right)
            {//测距
                ruleEndPosition = new PointF();
                ruleEndPosition.X = e.X - MapOriginLineW;
                ruleEndPosition.Y = e.Y - MapOriginLineL;
                pictureBox1.Invalidate();
            }
        }

        // 开启测距模式（右键拖动显示距离与方位角）。
        private void button13_Click(object sender, EventArgs e)
        {
            flag_distance = true;
        }

        // 自主定点选点开始：左键点击地图可新增航点。
        private void button11_Click(object sender, EventArgs e)
        {//自主定点选点开始
            flag_autofixedpoint = true;
        }

        // 自主定点选点结束。
        private void button12_Click(object sender, EventArgs e)
        {//自主定点选点结束
            flag_autofixedpoint = false;
        }

        // 导出自主定点航路到 Point_File.xml（含任务头信息 + 各航点字段）。
        private void button14_Click(object sender, EventArgs e)
        {//自主定点生成文件
            XmlDocument xmldoc = new XmlDocument();
            XmlDeclaration xmlde = xmldoc.CreateXmlDeclaration("1.0","utf-8","yes");
            xmldoc.AppendChild(xmlde);
            //加入根元素
            XmlElement xmlelement = xmldoc.CreateElement("AutoPloitPoint");//TaskNumber=a TotalTimeout=c TotalNumber=d
            xmlelement.SetAttribute("TaskNumber", textBox15.Text);
            xmlelement.SetAttribute("TotalTimeout", textBox16.Text);
            xmlelement.SetAttribute("TotalNumber", Autofixedpoint.Count.ToString());
            textBox17.Text = Autofixedpoint.Count.ToString();
            xmldoc.AppendChild(xmlelement);
            XmlNode xmlrootnode = xmldoc.SelectSingleNode("AutoPloitPoint");
            //添加要素
            for (int i = 0; i < Autofixedpoint.Count; i++)
            {
                XmlElement xmlrootelement = xmldoc.CreateElement("Points");
                xmlrootelement.SetAttribute("Name", "Point"+(i+1).ToString());

                XmlElement pxmlele = xmldoc.CreateElement("TrackPoint");
                pxmlele.InnerText = (i+1).ToString();
                xmlrootelement.AppendChild(pxmlele);

                pxmlele = xmldoc.CreateElement("Longitude");
                pxmlele.InnerText = Autofixedpoint[i].Longitude.ToString("F6");
                xmlrootelement.AppendChild(pxmlele);

                pxmlele = xmldoc.CreateElement("Latitude");
                pxmlele.InnerText = Autofixedpoint[i].Lat.ToString("F6");;
                xmlrootelement.AppendChild(pxmlele);

                pxmlele = xmldoc.CreateElement("strategy");
                pxmlele.InnerText = Autofixedpoint[i].Control_Strategy.ToString();
                xmlrootelement.AppendChild(pxmlele);

                pxmlele = xmldoc.CreateElement("Parameter");
                pxmlele.InnerText = Autofixedpoint[i].Control_Param.ToString();
                xmlrootelement.AppendChild(pxmlele);

                pxmlele = xmldoc.CreateElement("MotorSetSpeed");
                pxmlele.InnerText = Autofixedpoint[i].Motor_Speed.ToString();
                xmlrootelement.AppendChild(pxmlele);

                pxmlele = xmldoc.CreateElement("Device");
                pxmlele.InnerText = Convert.ToString(Autofixedpoint[i].Device_Control,2).PadLeft(8,'0').ToString();
                xmlrootelement.AppendChild(pxmlele);

                xmlrootnode.AppendChild(xmlrootelement);
            }
            xmldoc.Save(Application.StartupPath + "\\Point_File.xml");
            MessageBox.Show("自主定点xml文件生成成功！");
        }

        // 清空自主定点航点（内存队列 + 表格）。
        private void button15_Click(object sender, EventArgs e)
        {//清除点
            autofixedpointNUM = 0;
            dataGridView1.Rows.Clear();
            Autofixedpoint.Clear();
        }

        // 主窗体关闭时释放通信资源。
        private void Form1_FormClosing(object sender, FormClosingEventArgs e)
        {
            thread_rec.Abort();
            udp_send_recv.Close();
        }

        // 打开端口设置窗体（Form3），单实例复用。
        private void SetToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if (Form_set == null)
            {
                Form_set = new Form3(this);
                Form_set.Visible = true;
                Form_set.TopMost = true;
            }
            else
                Form_set.WindowState = FormWindowState.Normal;
        }

        // 航点表格编辑回写：用户改动后同步到 Autofixedpoint 内存结构。
        private void dataGridView1_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            int i = e.RowIndex;
            AutoFixedPoint newpoint = new AutoFixedPoint();
            newpoint.Longitude = Convert.ToDouble(dataGridView1.Rows[i].Cells[1].Value);
            newpoint.Lat = Convert.ToDouble(dataGridView1.Rows[i].Cells[2].Value);
            newpoint.Control_Strategy = ((dataGridView1.Rows[i].Cells[3].Value.ToString() == "定深") ? (Byte)0 : (Byte)1);
            newpoint.Control_Param = Convert.ToSingle(dataGridView1.Rows[i].Cells[4].Value);
            newpoint.Motor_Speed = Convert.ToInt16(dataGridView1.Rows[i].Cells[5].Value);
            newpoint.Device_Control = Convert.ToByte(dataGridView1.Rows[i].Cells[6].Value);
            Autofixedpoint[i] = newpoint;
        }

        // ASCII 十六进制转换调试按钮。
        private void button16_Click(object sender, EventArgs e)
        {
            Byte A=(Byte)'a';
            Byte B=(Byte)'8';
            Byte aa=addxxj(A,B);
            MessageBox.Show("0x"+aa.ToString("X2"));
        }
    }
}
