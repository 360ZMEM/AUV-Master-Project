using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using System.IO.Ports;
using System.IO;
namespace Console
{
    public partial class Form3 : Form
    {
        // Form3 是端口与网络配置窗口：
        // - 读取/保存 Application.StartupPath 下的 port_set.txt（固定 6 行）
        // - 配置内容会在下次主程序启动时生效
        private Form1 form1;
        public Form3(Form1 form1)
        {
            InitializeComponent();
            this.form1 = form1;
        }

        private void Form3_FormClosing(object sender, FormClosingEventArgs e)
        {
            // 清空主窗体中的引用，防止重复实例。
            form1.Form_set = null;
        }

        private void Form3_Load(object sender, EventArgs e)
        {
            // 加载当前系统串口列表，供用户选择无线电/北斗串口。
            string[] portnames = SerialPort.GetPortNames();
            foreach (string str in portnames)
            {
                comboBox1.Items.Add(str);
                comboBox2.Items.Add(str);
            }

            // 读取端口配置文件（固定 6 行）：
            // 1. 无线电串口 2. 北斗串口 3. 控制台IP 4. 控制台端口 5. AUV IP 6. AUV端口
            using (StreamReader sr = new StreamReader(Application.StartupPath.ToString() + @"\port_set.txt"))//读取端口配置文件
            {
                String line;
                line = sr.ReadLine();//读取第1行
                label6.Text = line;
               
                line = sr.ReadLine();//读取2行
                label7.Text = line;

                line = sr.ReadLine();//读取3行
                textBox2.Text = line;

                line = sr.ReadLine();//读取4行
                textBox3.Text = line;

                line = sr.ReadLine();//读取5行
                textBox8.Text = line;

                line = sr.ReadLine();//读取6行
                textBox1.Text = line;
                sr.Close();
            }
        }

        private void button34_Click(object sender, EventArgs e)
        {//修改端口配置文件（按固定 6 行顺序写入）
            using (StreamWriter sw = new StreamWriter(Application.StartupPath.ToString() + @"\port_set.txt"))
            {
                sw.WriteLine(comboBox1.SelectedItem.ToString());
                sw.WriteLine(comboBox2.SelectedItem.ToString());
                sw.WriteLine(textBox2.Text);
                sw.WriteLine(textBox3.Text);
                sw.WriteLine(textBox8.Text);
                sw.WriteLine(textBox1.Text);
                sw.Close();
            }

            // 重新读取并回显，确保界面显示的是文件中最终内容。
            using (StreamReader sr = new StreamReader(Application.StartupPath.ToString() + @"\port_set.txt"))//读取端口配置文件
            {
                String line;
                line = sr.ReadLine();//读取第1行
                label6.Text = line;

                line = sr.ReadLine();//读取2行
                label7.Text = line;

                line = sr.ReadLine();//读取3行
                textBox2.Text = line;

                line = sr.ReadLine();//读取4行
                textBox3.Text = line;

                line = sr.ReadLine();//读取5行
                textBox8.Text = line;

                line = sr.ReadLine();//读取6行
                textBox1.Text = line;
                sr.Close();
            }
            // 保存成功后提示重启：主程序在启动阶段读取配置，不做热重载。
            MessageBox.Show("端口配置文件修改成功，请重新开启软件!");
        }
    }
}
