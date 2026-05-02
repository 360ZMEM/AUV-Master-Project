using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;

namespace Console
{
    public partial class Form2 : Form
    {
        // Form2 是扩展控制面板：
        // 1) 通过 form1.work_instruct 向主窗体写入“单字节工作指令”；
        // 2) 通过定时器反向读取当前指令并高亮按钮，保证主/扩展界面状态一致；
        // 3) 通过文本框回车输入电机/舵角/调参，写入 Form1 的发送变量。
        private Form1 form1;
        public Form2(Form1 form1)
        {
            InitializeComponent();
            this.form1 = form1;
        }

        private void Form2_FormClosing(object sender, FormClosingEventArgs e)
        {
            // 关闭扩展窗口时只释放自身状态，不关闭主窗体。
            timer1.Stop();
            form1.Form_extend = null;
        }

        private void Form2_Load(object sender, EventArgs e)
        {
            // 200ms 刷新一次按钮高亮，体现当前 work_instruct 状态。
            timer1.Interval = 200;
            timer1.Enabled = true;
            timer1.Start();
        }

        private void timer1_Tick(object sender, EventArgs e)
        {
            // 根据主窗体当前指令高亮对应按钮。
            // 说明：Form2 不直接发送报文，真正发送在 Form1.timer1_Tick 内完成。
            if (form1.work_instruct == 0x11)
            {//主推上电按下
                button4.BackColor = Color.SkyBlue;
            }
            else
            {
                button4.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x12)
            {//主推断电按下
                button5.BackColor = Color.SkyBlue;
            }
            else
            {  
                button5.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x13)
            {//侧推上电已按下
                button6.BackColor = Color.SkyBlue;
            }
            else
            {
                button6.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x14)
            {//侧推断电已按下
                button7.BackColor = Color.SkyBlue;
            }
            else
            {
                button7.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x15)
            {//水平舵上电已按下
                button8.BackColor = Color.SkyBlue;
            }
            else
            {
                button8.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x16)
            {//水平舵断电已按下
                button9.BackColor = Color.SkyBlue;
            }
            else
            {
                button9.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x17)
            {//垂直舵上电已按下
                button10.BackColor = Color.SkyBlue;
            }
            else
            {
                button10.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x18)
            {//垂直舵断电已按下
                button11.BackColor = Color.SkyBlue;
            }
            else
            {
                button11.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x19)
            {//应急压载上电已按下
                button12.BackColor = Color.SkyBlue;
            }
            else
            {
                button12.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x20)
            {//应急压载断电已按下
                button14.BackColor = Color.SkyBlue;
            }
            else
            {
                button14.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x21)
            {//DVL上电已按下
                button13.BackColor = Color.SkyBlue;
            }
            else
            {
                button13.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x22)
            {//DVL断电已按下
                button15.BackColor = Color.SkyBlue;
            }
            else
            {
                button15.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x23)
            {//罗经上电已按下
                button16.BackColor = Color.SkyBlue;
            }
            else
            {
                button16.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x24)
            {//罗经断电已按下
                button17.BackColor = Color.SkyBlue;
            }
            else
            {
                button17.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x25)
            {//备用1上电已按下
                button18.BackColor = Color.SkyBlue;
            }
            else
            {
                button18.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x26)
            {//备用1断电已按下
                button19.BackColor = Color.SkyBlue;
            }
            else
            {
                button19.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x27)
            {//备用2上电已按下
                button20.BackColor = Color.SkyBlue;
            }
            else
            {
                button20.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x28)
            {//备用2断电已按下
                button21.BackColor = Color.SkyBlue;
            }
            else
            {
                button21.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x41)
            {//下潜测试已按下
                button22.BackColor = Color.SkyBlue;
            }
            else
            {
                button22.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x42)
            {//备用测试已按下
                button23.BackColor = Color.SkyBlue;
            }
            else
            {
                button23.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x51)
            {//参数调整开已按下
                button24.BackColor = Color.SkyBlue;
            }
            else
            {
                button24.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x52)
            {//参数调整关已按下
                button25.BackColor = Color.SkyBlue;
            }
            else
            {
                button25.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x53)
            {//备用调整开已按下
                button26.BackColor = Color.SkyBlue;
            }
            else
            {
                button26.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x54)
            {//备用调整关已按下
                button27.BackColor = Color.SkyBlue;
            }
            else
            {
                button27.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x61)
            {//查询指令1已按下
                button29.BackColor = Color.SkyBlue;
            }
            else
            {
                button29.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x62)
            {//查询指令2已按下
                button31.BackColor = Color.SkyBlue;
            }
            else
            {
                button31.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x71)
            {//定向航行开已按下
                button30.BackColor = Color.SkyBlue;
            }
            else
            {
                button30.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x72)
            {//定向航行关已按下
                button33.BackColor = Color.SkyBlue;
            }
            else
            {
                button33.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x73)
            {//航行控制指令--备用开已按下
                button28.BackColor = Color.SkyBlue;
            }
            else
            {
                button28.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x74)
            {//航行控制指令--备用关已按下
                button32.BackColor = Color.SkyBlue;
            }
            else
            {
                button32.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x81)
            {//载荷指令1已按下
                button34.BackColor = Color.SkyBlue;
            }
            else
            {
                button34.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x82)
            {//载荷指令2已按下
                button35.BackColor = Color.SkyBlue;
            }
            else
            {
                button35.BackColor = Color.Transparent;
            }
            if (form1.work_instruct == 0x83)
            {//载荷指令3已按下
                button36.BackColor = Color.SkyBlue;
            }
            else
            {
                button36.BackColor = Color.Transparent;
            }
        }

        // 以下 button4~button36 处理函数遵循统一的“同码切换”策略：
        // - 若当前指令 != 目标码：写入目标码（触发该动作）
        // - 若当前指令 == 目标码：回写 0x00（清空动作）
        // 这样可避免持续下发同一动作，且让操作者可用二次点击撤销。
        private void button4_Click(object sender, EventArgs e)
        {//主推上电（0x11）
            if (form1.work_instruct != 0x11)
            {
                form1.work_instruct = 0x11;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button5_Click(object sender, EventArgs e)
        {//主推断电（0x12）
            if (form1.work_instruct != 0x12)
            {
                form1.work_instruct = 0x12;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button6_Click(object sender, EventArgs e)
        {//侧推上电（0x13）
            if (form1.work_instruct != 0x13)
            {
                form1.work_instruct = 0x13;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button7_Click(object sender, EventArgs e)
        {//侧推断电（0x14）
            if (form1.work_instruct != 0x14)
            {
                form1.work_instruct = 0x14;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button8_Click(object sender, EventArgs e)
        {//水平舵上电（0x15）
            if (form1.work_instruct != 0x15)
            {
                form1.work_instruct = 0x15;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button9_Click(object sender, EventArgs e)
        {//水平舵断电（0x16）
            if (form1.work_instruct != 0x16)
            {
                form1.work_instruct = 0x16;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button10_Click(object sender, EventArgs e)
        {//垂直舵上电（0x17）
            if (form1.work_instruct != 0x17)
            {
                form1.work_instruct = 0x17;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button11_Click(object sender, EventArgs e)
        {//垂直舵断电（0x18）
            if (form1.work_instruct != 0x18)
            {
                form1.work_instruct = 0x18;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button12_Click(object sender, EventArgs e)
        {//应急压载上电
            if (form1.work_instruct != 0x19)
            {
                form1.work_instruct = 0x19;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button14_Click(object sender, EventArgs e)
        {//应急压载断电
            if (form1.work_instruct != 0x20)
            {
                form1.work_instruct = 0x20;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button13_Click(object sender, EventArgs e)
        {//DVL上电
            if (form1.work_instruct != 0x21)
            {
                form1.work_instruct = 0x21;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button15_Click(object sender, EventArgs e)
        {//DVL断电
            if (form1.work_instruct != 0x22)
            {
                form1.work_instruct = 0x22;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button16_Click(object sender, EventArgs e)
        {//通信模块上电
            if (form1.work_instruct != 0x23)
            {
                form1.work_instruct = 0x23;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button17_Click(object sender, EventArgs e)
        {//通信模块断电
            if (form1.work_instruct != 0x24)
            {
                form1.work_instruct = 0x24;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button18_Click(object sender, EventArgs e)
        {//备用1上电
            if (form1.work_instruct != 0x25)
            {
                form1.work_instruct = 0x25;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button19_Click(object sender, EventArgs e)
        {//备用1断电
            if (form1.work_instruct != 0x26)
            {
                form1.work_instruct = 0x26;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button20_Click(object sender, EventArgs e)
        {//备用2上电
            if (form1.work_instruct != 0x27)
            {
                form1.work_instruct = 0x27;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button21_Click(object sender, EventArgs e)
        {//备用2断电
            if (form1.work_instruct != 0x28)
            {
                form1.work_instruct = 0x28;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button22_Click(object sender, EventArgs e)
        {//下潜测试
            if (form1.work_instruct != 0x41)
            {
                form1.work_instruct = 0x41;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button23_Click(object sender, EventArgs e)
        {//备用测试
            if (form1.work_instruct != 0x42)
            {
                form1.work_instruct = 0x42;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button24_Click(object sender, EventArgs e)
        {//参数调整开（0x51）
            if (form1.work_instruct != 0x51)
            {
                form1.work_instruct = 0x51;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button25_Click(object sender, EventArgs e)
        {//参数调整关
            if (form1.work_instruct != 0x52)
            {
                form1.work_instruct = 0x52;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button26_Click(object sender, EventArgs e)
        {//备用调整开
            if (form1.work_instruct != 0x53)
            {
                form1.work_instruct = 0x53;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button27_Click(object sender, EventArgs e)
        {//备用调整关
            if (form1.work_instruct != 0x54)
            {
                form1.work_instruct = 0x54;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button29_Click(object sender, EventArgs e)
        {//查询指令1
            if (form1.work_instruct != 0x61)
            {
                form1.work_instruct = 0x61;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button31_Click(object sender, EventArgs e)
        {//查询指令2 
            if (form1.work_instruct != 0x62)
            {
                form1.work_instruct = 0x62;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button30_Click(object sender, EventArgs e)
        {//定向航行开（0x71）
            if (form1.work_instruct != 0x71)
            {
                form1.work_instruct = 0x71;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button33_Click(object sender, EventArgs e)
        {//定向航行关
            if (form1.work_instruct != 0x72)
            {
                form1.work_instruct = 0x72;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button28_Click(object sender, EventArgs e)
        {//航行控制指令--备用开
            if (form1.work_instruct != 0x73)
            {
                form1.work_instruct = 0x73;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button32_Click(object sender, EventArgs e)
        {//航行控制指令--备用关
            if (form1.work_instruct != 0x74)
            {
                form1.work_instruct = 0x74;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button34_Click(object sender, EventArgs e)
        {//载荷指令1（0x81）
            if (form1.work_instruct != 0x81)
            {
                form1.work_instruct = 0x81;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button35_Click(object sender, EventArgs e)
        {//载荷指令2
            if (form1.work_instruct != 0x82)
            {
                form1.work_instruct = 0x82;
            }
            else
            {
                form1.work_instruct = 0x00;
            }
        }

        private void button36_Click(object sender, EventArgs e)
        {//载荷指令3（0x83）
            if (form1.work_instruct != 0x83)
            {
                form1.work_instruct = 0x83;
            }
            else
            {
                form1.work_instruct = 0x00;
            }

        }

        private void textBox8_KeyPress(object sender, KeyPressEventArgs e)
        {//电机转速1输入（回车生效，范围 -1500~1500 rpm）
            Int16 tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToInt16(textBox8.Text);
                    if (tmp >= -1500 && tmp <= 1500)
                    {
                        form1.MotorSpeed1 = tmp;
                    }
                    else
                        MessageBox.Show("输入的电机转速1不在-1500到1500范围内！");
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入电机转速1！");
                }
            }
        }

        private void textBox9_KeyPress(object sender, KeyPressEventArgs e)
        {//电机转速2输入（回车生效，范围 -4000~4000 rpm）
            Int16 tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToInt16(textBox9.Text);
                    if (tmp >= -4000 && tmp <= 4000)
                    {
                        form1.MotorSpeed2 = tmp;
                    }
                    else
                        MessageBox.Show("输入的电机转速2不在-4000到4000范围内！");
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入电机转速2！");
                }
            }
        }

        private void textBox10_KeyPress(object sender, KeyPressEventArgs e)
        {//左水平舵角输入（用户输入角度，内部按 ×10 缩放保存）
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox10.Text);
                    tmp = (tmp * 10);
                    if (tmp >= -300 && tmp <= 300)
                    {
                        form1.RudderAngle_LH = (Int16)tmp;
                    }
                    else
                        MessageBox.Show("输入的左水平舵角不在-30到30范围内！");
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入左水平舵角！");
                }
            }
        }

        // textBox21~textBox25/26 为调参输入：
        // - 参数1~4：输入浮点后按 ×1,000,000 存入 Int32
        // - 参数5~8：输入浮点后按 ×10,000 存入 Int16
        // - 参数9~12：输入浮点后按 ×1,000 存入 Int16
        // 与 Form1 打包协议字段缩放规则保持一致。

        private void textBox11_KeyPress(object sender, KeyPressEventArgs e)
        {//右水平舵角输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox11.Text);
                    tmp = (tmp * 10);
                    if (tmp >= -300 && tmp <= 300)
                    {
                        form1.RudderAngle_RH = (Int16)tmp;
                    }
                    else
                        MessageBox.Show("输入的右水平舵角不在-30到30范围内！");
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入右水平舵角！");
                }
            }
        }

        private void textBox12_KeyPress(object sender, KeyPressEventArgs e)
        {//上垂直舵输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox12.Text);
                    tmp = (tmp * 10);
                    if (tmp >= -300 && tmp <= 300)
                    {
                        form1.RudderAngle_UV = (Int16)tmp;
                    }
                    else
                        MessageBox.Show("输入的上垂直舵角不在-30到30范围内！");
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入上垂直舵角！");
                }
            }
        }

        private void textBox13_KeyPress(object sender, KeyPressEventArgs e)
        {//下垂直舵输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox13.Text);
                    tmp = (tmp * 10);
                    if (tmp >= -300 && tmp <= 300)
                    {
                        form1.RudderAngle_LV = (Int16)tmp;
                    }
                    else
                        MessageBox.Show("输入的下垂直舵角不在-30到30范围内！");
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入下垂直舵角！");
                }
            }
        }

        private void textBox14_KeyPress(object sender, KeyPressEventArgs e)
        {//定向角度输入
            UInt16 tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToUInt16(textBox14.Text);
                    if (tmp >= 0 && tmp <=359)
                    {
                        form1.OrientationAngle = tmp;
                    }
                    else
                        MessageBox.Show("输入的定向角度不在0到360范围内！");
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入定向角度！");
                }
            }
        }

        private void textBox21_KeyPress(object sender, KeyPressEventArgs e)
        {//调参1输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox21.Text);
                    tmp = (tmp * 1000000);
                        form1.Parameter1 = (Int32)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参1！");
                }
            }
        }

        private void textBox20_KeyPress(object sender, KeyPressEventArgs e)
        {//调参2输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox20.Text);
                    tmp = (tmp * 1000000);
                    form1.Parameter2 = (Int32)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参2！");
                }
            }
        }

        private void textBox19_KeyPress(object sender, KeyPressEventArgs e)
        {//调参3输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox19.Text);
                    tmp = (tmp * 1000000);
                    form1.Parameter3 = (Int32)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参3！");
                }
            }
        }

        private void textBox17_KeyPress(object sender, KeyPressEventArgs e)
        {//调参4输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox17.Text);
                    tmp = (tmp * 1000000);
                    form1.Parameter4 = (Int32)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参4！");
                }
            }
        }

        private void textBox18_KeyPress(object sender, KeyPressEventArgs e)
        { //调参5输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox18.Text);
                    tmp = (tmp * 10000);
                    form1.Parameter5 = (Int16)tmp;
                    //MessageBox.Show(form1.Parameter5.ToString());
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参5！");
                }
            }
        }

        private void textBox16_KeyPress(object sender, KeyPressEventArgs e)
        {//调参6输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox16.Text);
                    tmp = (tmp * 10000);
                    form1.Parameter6 = (Int16)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参6！");
                }
            }

        }

        private void textBox15_KeyPress(object sender, KeyPressEventArgs e)
        {//调参7输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox15.Text);
                    tmp = (tmp * 10000);
                    form1.Parameter7 = (Int16)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参7！");
                }
            }
        }

        private void textBox22_KeyPress(object sender, KeyPressEventArgs e)
        {//调参8输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox22.Text);
                    tmp = (tmp * 10000);
                    form1.Parameter8 = (Int16)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参8！");
                }
            }
        }

        private void textBox23_KeyPress(object sender, KeyPressEventArgs e)
        {//调参9输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox23.Text);
                    tmp = (tmp * 1000);
                    form1.Parameter9 = (Int16)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参9！");
                }
            }
        }

        private void textBox24_KeyPress(object sender, KeyPressEventArgs e)
        {//调参10输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox24.Text);
                    tmp = (tmp * 1000);
                    form1.Parameter10 = (Int16)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参10！");
                }
            }
        }

        private void textBox26_KeyPress(object sender, KeyPressEventArgs e)
        {//调参11输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox26.Text);
                    tmp = (tmp * 1000);
                    form1.Parameter11 = (Int16)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参11！");
                }
            }
        }

        private void textBox25_KeyPress(object sender, KeyPressEventArgs e)
        {//调参12输入
            double tmp = 0;
            if (e.KeyChar == 13)//按下回车有效
            {
                try
                {
                    tmp = Convert.ToDouble(textBox25.Text);
                    tmp = (tmp * 1000);
                    form1.Parameter12 = (Int16)tmp;
                }
                catch (Exception em)
                {
                    MessageBox.Show("请正确输入调参12！");
                }
            }
        }
    }
}
