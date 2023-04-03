from json import load, dump
from io import BytesIO
import json
import requests
import base64
from nonebot import get_bot, on_command
from hoshino import priv
from hoshino.typing import NoticeSession, MessageSegment, CQHttpError
from .pcrclient import pcrclient, ApiException, bsdkclient
from asyncio import Lock
from os.path import dirname, join, exists
from copy import deepcopy
from traceback import format_exc
from .safeservice import SafeService
from hoshino.util import pic2b64
from random import randint
import time
import os
from time import gmtime
from hoshino.modules.priconne import chara
from hoshino.modules.priconne._pcr_data import CHARA_NAME
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter, ImageOps
from hoshino import util


sv_help = '''
[游戏内会战推送] 无描述
'''.strip()
sv = SafeService('会战推送',help_=sv_help, bundle='pcr查询')
curpath = dirname(__file__)

##############################
forward_group_list = [1148952351,452983159]


current_folder = os.path.dirname(__file__)
img_file = os.path.join(current_folder, 'img')

cache = {}
client = None
lck = Lock()

captcha_lck = Lock()

with open(join(curpath, 'account.json')) as fp:
    acinfo = load(fp)

bot = get_bot()
validate = None
validating = False
acfirst = False


async def captchaVerifier(gt, challenge, userid):
    global acfirst, validating
    if not acfirst:
        await captcha_lck.acquire()
        acfirst = True
    
    if acinfo['admin'] == 0:
        bot.logger.error('captcha is required while admin qq is not set, so the login can\'t continue')
    else:
        url = f"https://help.tencentbot.top/geetest/?captcha_type=1&challenge={challenge}&gt={gt}&userid={userid}&gs=1"
        await bot.send_private_msg(
            user_id = acinfo['admin'],
            message = f'pcr账号登录需要验证码，请完成以下链接中的验证内容后将第一行validate=后面的内容复制，并用指令{P}/pcrval xxxx将内容发送给机器人完成验证\n验证链接：{url}'
        )
    validating = True
    await captcha_lck.acquire()
    validating = False
    return validate

async def errlogger(msg):
    await bot.send_private_msg(
        user_id = acinfo['admin'],
        message = f'pcrjjc2登录错误：{msg}'
    )

bclient = bsdkclient(acinfo, captchaVerifier, errlogger)
client = pcrclient(bclient)

qlck = Lock()
usually_status = []
reward_list = []
mtdict = {}

async def verify():     #验证登录状态
    if validating:
        raise ApiException('账号被风控，请联系管理员输入验证码并重新登录', -1)
    async with qlck:
        while client.shouldLogin:
            await client.login()
            time.sleep(3)
    return

@on_command(f'/pcrval')     #原手动验证
async def validate(session):
    global binds, lck, validate
    if session.ctx['user_id'] == acinfo['admin']:
        validate = session.ctx['message'].extract_plain_text().strip()[8:]
        captcha_lck.release()

swa = 0
pre_push = [[],[],[],[],[]]
coin = 0
arrow = 0
sw = 0      #会战推送开关
fnum = 0
arrow_rec = 0
side = {
    1: 'A',
    4: 'B',
    11: 'C',
    35: 'D',
    45: 'E'
    
}
curr_side = '_'

@sv.scheduled_job('interval', seconds=20)
async def teafak():
    global coin,arrow_rec,side,curr_side,arrow,sw,pre_push,fnum,forward_group_list
    if sw == 0:     #会战推送开关
        return
    if coin == 0:   #初始化获取硬币数
        item_list = {}
        await verify()
        load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})   #获取会战币api
        for item in load_index["item_list"]:
            item_list[item["id"]] = item["stock"]
        coin = item_list[90006]
    msg = ''
    ref = 0
    res = 0
    
    while(ref == 0):
        try:
            await verify()
            clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
            clan_id = clan_info['clan']['detail']['clan_id']
            res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
            ref = 1
        except:
            await verify()
            load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})   #击败BOSS时会战币会变动
            item_list = {}
            for item in load_index["item_list"]:
                item_list[item["id"]] = item["stock"]
            coin = item_list[90006]
            pass
        
    if res != 0:
        next_lap = res['lap_num']    #当前周目
        for side1 in side:          #计算面数
            if next_lap > side1:
                next_lap_1 = side[side1]
            else:
                break
        if curr_side != next_lap_1:
            curr_side = next_lap_1
            msg += f'[CQ:at,qq=all]当前到达{curr_side}面，注意调整出刀阵容!'
        next_boss = 1
        info = res['boss_info'] #BOSS状态
        
        history = reversed(res['damage_history'])   #从返回的出刀记录刀的状态
        clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
        clan_id = clan_info['clan']['detail']['clan_id']
        pre_clan_battle_id = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
        #print(res)
        
        clan_battle_id = pre_clan_battle_id['clan_battle_id']
        for hst in history:
            if (arrow != 0) and (hst['history_id'] <= arrow):   #记录刀ID防止重复
                continue
                
            name = hst['name']  #名字
            vid = hst['viewer_id']  #13位ID
            kill = hst['kill']  #是否击杀
            damage = hst['damage']  #伤害
            lap = hst['lap_num']    #圈数
            boss = int(hst['order_num'])    #几号boss
            ctime = hst['create_time']  #出刀时间
            real_time = time.localtime(ctime)   
            day = real_time[2]  #垃圾代码
            hour = real_time[3]
            minu = real_time[4]
            seconds = real_time[5]
            arrow = hst['history_id']   #记录指针
            enemy_id = hst['enemy_id']  #BOSSID，暂时没找到用处
            if boss == 5:   #下一圈和下一个boss逻辑，反正要改会战了，凑合用着
                next_boss = 1
                next_lap = lap + 1
            else:
                next_boss = boss + 1
                next_lap = lap
            ifkill = ''     #击杀变成可读
            if kill == 1:
                ifkill = '并击破'
                if boss == 5:   #我为啥要这么写
                    push_list = pre_push[0]
                elif boss != 5:
                    push_list = pre_push[next_boss-1]
                
                if push_list != []:     #预约后群内和行会内提醒
                    await verify()
                    chat_content = f'{next_lap}周目{next_boss}王已被预约，请耐心等候！'

                    await client.callapi('/clan/chat', {'clan_id': clan_id, 'type': 0, 'message': chat_content})
                    warn = ''
                    for pu in push_list:
                        pu = pu.split('|')
                        uid = int(pu[0])
                        gid = int(pu[1])
                        atmsg = f'提醒：已到{next_lap}周目 {next_boss} 王！请注意沟通上一尾刀~\n[CQ:at,qq={uid}]'
                        await bot.send_group_msg(group_id = gid,message = atmsg)
                    pre_push[next_boss-1] = []
                #push = True
            msg += f'[{curr_side}]{name} 对 {lap} 周目 {boss} 王造成了 {damage} 伤害{ifkill}\n'
            output = f'{day},{hour},{minu},{seconds},{arrow},{name},{vid},{lap},{boss},{damage},{kill},{enemy_id}'  #记录出刀，后面要用
            with open(current_folder+"/Output.txt","a",encoding='utf-8') as file:   #windows这么写是不是会有问题
                #if output not in file:
                file.write(str(output)+'\n')
                file.close()                
        boss_info2 = await client.callapi('/clan_battle/boss_info', {'clan_id': clan_id, 'clan_battle_id': clan_battle_id, 'lap_num': next_lap, 'order_num': next_boss})  #这里找一下获取会战id的api，应该top就有，晚点更新
        #print(boss_info2)
        fnum1 = boss_info2['fighter_num']
        
        if fnum == 0:
            if arrow_rec == 0:
                arrow_rec = arrow

        if fnum < fnum1:    #垃圾代码，后面记录人数
            fnum = fnum1
            msg += f'90秒内有{fnum}名玩家正在实战'
        elif fnum > fnum1:
            fnum = fnum1
            if arrow_rec != arrow:
                msg += f'90秒内有{fnum}名玩家正在实战'
                arrow_rec = arrow
            else:
                msg += f'90秒内有{fnum}名玩家正在实战,但是有玩家并没有结算,请注意沟通进行中的出刀'
        elif fnum == fnum1:
            if arrow_rec != arrow:
                msg += f'90秒内有{fnum}名玩家正在实战'
                arrow_rec = arrow
        if msg != '':
            if len(msg)>200:
                msg = '...\n' + msg[-200:] 
            for forward_group in forward_group_list:
                await bot.send_group_msg(group_id = forward_group,message = msg)
    else:
        print('error')
            

@sv.on_fullmatch('切换会战推送')    #这个给要出刀的号准备的
async def sw_pus(bot , ev):
    global sw
    if sw == 0:
        sw = 1
        await bot.send(ev,'已开启会战推送')
    else:
        sw = 0
        await bot.send(ev,'已关闭会战推送')


@sv.on_fullmatch('初始化会战推送')  #会战前一天输入这个
async def sw_pus(bot , ev):
    global swa
    swa = 1
    await bot.send(ev,'初始化完成')
    
@sv.on_prefix('会战预约')   #会战预约5
async def preload(bot , ev):
    global pre_push
    num = ev.message.extract_plain_text().strip()
    try:
        if int(num) not in [1,2,3,4,5]:
            await bot.send(ev,'点炒饭是吧，爬！')
            return
        else:
            num = int(num)
            qid = str(ev.user_id) + '|' + str(ev.group_id)
            pus = pre_push[num-1]
            warn = ''
            clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
            clan_id = clan_info['clan']['detail']['clan_id']
            if pus != []:
                warn = f'注意：多于1人同时预约了{num}王，请注意出刀情况!'
            if qid not in pus:
                pus.append(qid)
                await bot.send(ev,f'预约{num}王成功!\n{warn}',at_sender=True)
                if sw == 1:
                    pp1 = ev.user_id
                    name = ''
                    try:
                        info = await bot.get_stranger_info(self_id=ev.self_id, user_id=pp1)
                        name = info['nickname'] or pp1
                        name = util.filt_message(name)
                    except CQHttpError as e:
                        print('error name')
                        pass
                    await verify()
                    chat_content = f'一位行会成员({name})预约了{num}王，请注意出(撞)刀情况。{warn}'
                    await client.callapi('/clan/chat', {'clan_id': clan_id, 'type': 0, 'message': chat_content})
            else:
                pus.remove(qid)
                await bot.send(ev,f'你取消预约了{num}王！',at_sender=True)
                if sw == 1:
                    chat_content = f'一位行会成员取消预约了{num}王!'
                    await client.callapi('/clan/chat', {'clan_id': clan_id, 'type': 0, 'message': chat_content})
                    
    except:
        await bot.send(ev,'点炒饭是吧，爬！')
        pass
    
@sv.on_fullmatch('会战表')  #预约列表
async def sw_plist(bot , ev):
    num = 0
    msg  = ''
    for p in pre_push:
        num += 1
        msg += f'{num}王预约列表\n'
        for pp in p:
            pp = pp.split('|')
            print(pp)
            pp1 = int(pp[0])
            
            try:
                info = await bot.get_stranger_info(self_id=ev.self_id, user_id=pp1)
                name = info['nickname'] or pp1
                name = util.filt_message(name)
            except CQHttpError as e:
                print('error name')
                pass
            msg += f'+{name}\n'
    await bot.send(ev,msg)
    
@sv.on_fullmatch('清空预约表')
async def cle(bot , ev): 
    global pre_push
    pre_push = pre_push = [[],[],[],[],[]]
    await bot.send(ev,'已全部清空')
    
@sv.on_fullmatch('会战帮助')
async def chelp(bot , ev): 
    # msg = '[查轴[A/B/C/D/E][S/T/TS][1/2/3/4/5][ID]]:查轴，中括号内为选填项，可叠加使用。*S/T/TS分别表示手动/自动/半自动*\n[分刀[A/B/C/D/E][毛分/毛伤][S/T/TS][1/2/3/4/5]]:根据box分刀，中括号内为选填项，可叠加使用。*可选择限定boss，如123代表限定123王*\n[(添加/删除)(角色/作业)黑名单 + 名称或ID]:支持多角色，例如春环环奈，无空格。作业序号：花舞作业的序号，如‘A101’\n[(添加/删除)角色缺失 + 角色名称]:支持多角色，例如春环环奈，无空格\n[查看(作业黑名单/角色缺失/角色黑名单)]\n[清空(作业黑名单/角色缺失/角色黑名单)]\n[切换会战推送]:打开/关闭会战推送\n[会战预约(1/2/3/4/5)]:预约提醒\n[会战表]:查看所有预约\n[编写中...][会战查刀(ID)]:查看出刀详情\n[查档线]:若参数为空，则输出10000名内各档档线；若有多个参数，请使用英文逗号隔开。\n[清空预约表]:(仅SU可用)\n'
    msg = '[初始化会战推送]:会战前一天输入这个，记得清空Output.txt内的内容，不要删除Output.txt\n[切换会战推送]:打开/关闭会战推送\n[会战预约(1/2/3/4/5)]:预约提醒\n[会战表]:查看所有预约\n[清空预约表]:(仅SU可用)\n'
    await bot.send(ev,msg)


def rounded_rectangle(size, radius, color):     #ChatGPT帮我写的，我也不会
    width, height = size
    rectangle = Image.new("RGBA", size, color)
    corner = Image.new("RGBA", (radius, radius), (0, 0, 0, 0))
    filled_corner = Image.new("RGBA", (radius, radius), (0, 0, 0, 255))
    mask = Image.new("L", (radius, radius), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, radius * 2, radius * 2), fill=255)

    corner.paste(filled_corner, (0, 0), mask)

    rectangle.paste(corner, (0, 0))
    rectangle.paste(corner.rotate(90), (0, height - radius))
    rectangle.paste(corner.rotate(180), (width - radius, height - radius))
    rectangle.paste(corner.rotate(270), (width - radius, 0))

    return rectangle

def format_number_with_commas(number):      #这个也是他帮我写的
    return '{:,}'.format(number)

#@sv.on_fullmatch('输出会战日志')       #服务器不同
async def cout(bot , ev): 
    cfile = current_folder+ '/Output.txt'
    now = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
    name = f'Output - Log {now}'
    await bot.upload_group_file(group_id = ev.group_id, file = cfile, name = name)
    await bot.send(ev, '上传完成')


@sv.on_fullmatch('会战状态')    #这个更是重量级
async def status(bot,ev):
    boss_ooo = [305700,302000,300602,304101,300100]
    #try:
    await bot.send(ev,'生成中...')
    ##第一部分
    img = Image.open(img_file+'/cbt.png')
    draw = ImageDraw.Draw(img)
    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 25)
    await verify()
    
    load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
    clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
    clan_id = clan_info['clan']['detail']['clan_id']
    item_list = {}
    for item in load_index["item_list"]:
        item_list[item["id"]] = item["stock"]
    coin = item_list[90006]   
    res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
    #print(res)
    
    clan_battle_id = res['clan_battle_id']
    clan_name = res['user_clan']['clan_name']
    draw.text((1340,50), f'{clan_name}', font=setFont, fill="#A020F0")
    rank = res['period_rank']
    draw.text((1340,170), f'{rank}', font=setFont, fill="#A020F0")
    lap = res['lap_num']
    img_num = 0 
    for boss in res['boss_info']:
        boss_num = boss['order_num']
        boss_id = boss['enemy_id']
        mhp = boss['max_hp']
        hp = boss['current_hp']
        hp_percentage = hp / mhp  # 计算血量百分比
    
        # 根据血量百分比设置血条颜色
        if hp_percentage > 0.5:
            hp_color = "lightgreen"
        elif 0.25 < hp_percentage <= 0.5:
            hp_color = "orange"
        else:
            hp_color = "red"
    
        length = int((hp / mhp) * 1180)
        hp_bar = rounded_rectangle((length, 95), 10, hp_color)
        img.paste(hp_bar, (80, 40 + (boss_num - 1) * 142), hp_bar)
        try:    #晚点改
            img2 = Image.open(f'/data_new/Hoshino/res/img/priconne/unit/{boss_ooo[img_num]}.png')
            img_num += 1
            img2 = img2.resize((64,64),Image.ANTIALIAS)
            img.paste(img2, (93, 50+(boss_num-1)*142))
        except:
            pass
        
        # 在BOSS血条循环中
        bg_color = (0, 0, 0, 128)  # 半透明黑色背景
        bg_width = 300  # 背景宽度
        bg_height = 35  # 背景高度
        
        # 绘制半透明背景
        bg = Image.new('RGBA', (bg_width, bg_height), bg_color)
        img.paste(bg, (160, 38+(boss_num-1)*142), bg)
        
        draw.text((160, 40+(boss_num-1)*142), f'{format_number_with_commas(hp)}/{format_number_with_commas(mhp)}', font=setFont, fill="#FFFFFF")
        
        
        pre = pre_push[boss_num-1]
        all_name = ''
        if pre != []:
            
            for pu in pre:
                pu = pu.split('|')
                uid = int(pu[0])
                gid = int(pu[1])
        
        
                pp1 = uid
                name = ''
                try:
                    info = await bot.get_stranger_info(self_id=ev.self_id, user_id=pp1)
                    name = info['nickname'] or pp1
                    name = util.filt_message(name)
                    all_name += f'{name} '
                except CQHttpError as e:
                    print('error name')
                    pass
        if all_name != '':
            all_name+='已预约'
            draw.text((160, 80+(boss_num-1)*142), f'{all_name}', font=setFont, fill="#A020F0")
        else:
            draw.text((160, 80+(boss_num-1)*142), f'无人预约', font=setFont, fill="#A020F0")
        
    #第二部分    
    res2 = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 1})
    #print(res2)
    row = 0
    width = 0
    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 15)
    last_rank = res2['last_total_ranking']
    draw.text((1320, 320), f'上期排名:{last_rank}', font=setFont, fill="#A020F0")
    for members in res2['clan']['members']:
        vid = members['viewer_id']
        name = members['name']
        favor = members['favorite_unit']
        favorid = str(favor['id'])[:-2]
        stars = 3 if members['favorite_unit']['unit_rarity'] != 6 else 6
        try:
            img2 = Image.open(f'/data_new/Hoshino/res/img/priconne/unit/icon_unit_{favorid}{stars}1.png')
            img2 = img2.resize((48,48),Image.ANTIALIAS)
    
            img.paste(img2, (82+int(149.5*width), 761+int(59.8*row)), img2)
        except:
            pass

        

        kill_sign = 0
        kill_acc = 0
        todayt = time.localtime()
        hourh = todayt[3]
        today = 0
        if hourh < 5:
            today = todayt[2]-1
        else:
            today = todayt[2]
        
        #today = 26
        draw.text((1000,760), f'{today}日', font=setFont, fill="#A020F0")
        img3 = Image.new('RGB', (25, 17), "white")
        img4 = Image.new('RGB', (12, 17), "red")
        #img5 = Image.new('RGB', (25, 17), "green")
        for line in open(current_folder + "/Output.txt",encoding='utf-8'):
            if line != '':
                line = line.split(',')
                day = int(line[0])
                hour = int(line[1])
                re_battle_id = int(line[4])
                re_name = line[5]
                re_vid = line[6]
                re_lap = int(line[7])
                re_boss = int(line[8])
                re_dmg = int(line[9])
                re_kill = int(line[10])
                re_boss_id = int(line[11])
                if_today = False
                if (day == today and hour >= 5) or (day == today + 1 and hour < 5):
                    if_today = True
                if int(vid) == int(re_vid) and if_today == True:
                    if re_kill == 0 and kill_sign == 0:
                        kill_acc += 1
                        kill_sign = 0
                    elif re_kill == 0 and kill_sign == 1:
                        kill_acc += 0.5
                        kill_sign = 0
                    elif re_kill == 1 and kill_sign == 0:
                        kill_acc += 0.5
                        kill_sign = 1
                    elif re_kill == 1 and kill_sign == 1:
                        kill_acc += 0.5
                        kill_sign = 0
        
        if kill_acc == 0:
            draw.text((132+149*width, 761+60*row), f'{name}', font=setFont, fill="#FF0000")
        elif 0< kill_acc < 3:
            draw.text((132+149*width, 761+60*row), f'{name}', font=setFont, fill="#FF00FF")
        elif kill_acc == 3:
            draw.text((132+149*width, 761+60*row), f'{name}', font=setFont, fill="#00FF00")
        
        width2 = 0
        while kill_acc-1 >=0:
            img.paste(img3, (130+int(149.5*width)+30*width2, 785+60*row))
            kill_acc -= 1
            width2 += 1
        if kill_acc == 0.5:
            img.paste(img4, (130+int(149.5*width)+30*width2, 785+60*row))
            kill_acc -= 0.5
        #draw.text((132+149*width, 781+60*row), f'{kill_acc}', font=setFont, fill="#A020F0")
        width += 1
        if width == 6:
            width = 0
            row += 1    
            
    
    #第三部分
    if res != 0:
        
        info = res['boss_info'] #BOSS
        next_lap_1 = res['lap_num']    #周目
        next_boss = 1
        msg = ''
        history = res['damage_history']
        order = 0
        for hst in history:
            order += 1
            if order < 21:
                name = hst['name']
                vid = hst['viewer_id']
                kill = hst['kill']
                damage = hst['damage']
                lap = hst['lap_num']
                boss = int(hst['order_num'])
                ctime = hst['create_time']
                real_time = time.localtime(ctime)
                day = real_time[2]
                hour = real_time[3]
                minu = real_time[4]
                seconds = real_time[5]
                arrow = hst['history_id']
                #real_time = time.strftime('%d - %H:%M:%S', time.localtime(ctime))
                enemy_id = hst['enemy_id']
                if boss == 5:
                    next_boss = 1
                    next_lap = lap + 1
                else:
                    next_boss = boss + 1
                    next_lap = lap
                ifkill = ''
                if kill == 1:
                    ifkill = '并击破'
                    #push = True
                msg = f'[{day}日{hour}:{minu}]{name} 对 {lap} 周目 {boss} 王造成了 {damage} 伤害{ifkill}'
                if kill == 1:
                    draw.text((1320, 385+(order*15)), f'{msg}', font=setFont, fill="yellow")
                else:
                    draw.text((1320, 385+(order*15)), f'{msg}', font=setFont, fill="purple")
                if order == 1:
                    res3 = await client.callapi('/clan_battle/history_report', {'clan_id': clan_id, 'history_id': int(arrow)})
                    print(res3)
                    row = 0
                    for hi in res3['history_report']:
                        hvid = hi['viewer_id']
                        #hunit_id = hi['unit_id'] 
                        if hvid != 0:
                            hstars = hi['unit_rarity']
                            hdmg = hi['damage']
                            favorid = str(hi['unit_id'])[:-2]
                            stars = 3 if hstars != 6 else 6
                            try:
                                img2 = Image.open(f'/data_new/Hoshino/res/img/priconne/unit/icon_unit_{favorid}{stars}1.png')
                                img2 = img2.resize((48,48),Image.ANTIALIAS)
                                img.paste(img2, (1320,761+int(59.8*row)))
                            except:
                                pass
                            draw.text((1380,761+int(59.8*row)), f'伤害{hdmg}', font=setFont, fill="#A020F0")
                            row += 1
        draw.text((1320, 230), f'当前{next_lap_1}周目', font=setFont, fill="#A020F0")            
        
        fnum1 = -1
        try:
            boss_info2 = await client.callapi('/clan_battle/boss_info', {'clan_id': clan_id, 'clan_battle_id': clan_battle_id, 'lap_num': next_lap, 'order_num': next_boss})
            fnum1 = boss_info2['fighter_num']
        except:
            pass
        #print(boss_info2)
        
        draw.text((1020,860), f'当前有{fnum1}名玩家正在实战', font=setFont, fill="#A020F0")
    else:
        print('error')
    
    width = img.size[0]   # 获取宽度
    height = img.size[1]   # 获取高度
    img = img.resize((int(width*1), int(height*1)), Image.ANTIALIAS)    
    
    
    img = p2ic2b64(img)
    img = MessageSegment.image(img)
    await bot.send(ev, img)
    # except:
    #     await bot.send(ev,'发生不可预料的错误，请重试')
    #     pass

def p2ic2b64(img, quality=90):
    # 如果图像模式为RGBA，则将其转换为RGB模式
    if img.mode == 'RGBA':
        img_rgb = Image.new('RGB', img.size, (255, 255, 255))
        img_rgb.paste(img, mask=img.split()[3])  # 使用alpha通道作为mask
        img = img_rgb

    buf = BytesIO()
    img.save(buf, format='JPEG', quality=quality)
    base64_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    return 'base64://' + base64_str
    
@sv.scheduled_job('cron', hour='5') #推送5点时的名次
async def roo():
    global sw,swa,forward_group_list
    if sw == 1:
        await verify()
        try:
            load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
        except:
            load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
        item_list = {}
        for item in load_index["item_list"]:
            item_list[item["id"]] = item["stock"]
        coin = item_list[90006]
        clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
        clan_id = clan_info['clan']['detail']['clan_id']
        res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
        #print(res)
        rank = res['period_rank']
        msg = f'当前的排名为{rank}位'
        for forward_group in forward_group_list:
            await bot.send_group_msg(group_id = forward_group,message = msg)
            
        
    if swa == 1:
        sw = 1
        swa = 0