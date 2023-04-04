# 基于pcrjjc2的会战推送插件

**本项目基于AGPL v3协议开源**

## 配置方法

1. 打开hoshino插件文件夹
2. git clone https://github.com/AddOneSecondL/pcrjjc2-clanbattle.git
3. __init__.py 第32行改成需要推送的群
4. config文件里面添加pcrjjc2-clanbattle
5. account.json填上在会里的号的账号密码
6. 发送会战状态可以查看当前会战状态
7. 会战前一天请清空output.txt并输入初始化会战推送
8. 会战期间输入 切换会战推送 来打开/关闭推送，默认关闭
9. 关于查档线功能，结算时不能获取数据，官方结算完和会战开启时可以使用，通过获取游戏内数据，输入 查档线 可以查看各档档线，输入 查档线 1,2,3,4 可以查看 1,2,3,4 名详情，其他名次也是这样

自用改的渣代码，见谅(有大佬教我怎么获取res里的头像嘛，我只会绝对路径)
最终看起来应该是这样子的
![](example/1.jpg)

![](example/2.png)

查档线
![](example/3.png)