from json import load, dump
from io import BytesIO
import json
import requests
import base64
import random
from nonebot import get_bot, on_command
from hoshino import priv, R
from hoshino.typing import NoticeSession, MessageSegment, CQHttpError
from .pcrclient import pcrclient, ApiException, bsdkclient
from asyncio import Lock
from os.path import dirname, join, exists
from copy import deepcopy
from traceback import format_exc
from .safeservice import SafeService
from hoshino.util import pic2b64
from random import randint
import re
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

##############################下面这个框填要推送的群
forward_group_list = []


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
boss_status = [0,0,0,0,0]
in_game = [0,0,0,0,0]
pre_push = [[],[],[],[],[]]
coin = 0
arrow = 0
tvid = 0
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
phase = {
    1: 1,
    4: 2,
    11: 3,
    35: 4,
    45: 5
    
}
curr_side = '_'

# @sv.on_fullmatch('fffff')
# async def test2(bot,ev):
#     item_list = {}
#     await verify()
#     load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})   #获取会战币api
#     for item in load_index["item_list"]:
#         item_list[item["id"]] = item["stock"]
#     coin = item_list[90006]
#     clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
#     clan_id = clan_info['clan']['detail']['clan_id']
#     res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
#     print(res)


@sv.scheduled_job('interval', seconds=20)
async def teafak():
    global coin,arrow_rec,side,curr_side,arrow,sw,pre_push,fnum,forward_group_list,boss_status,in_game,tvid
    load_index = 0
    if sw == 0:     #会战推送开关
        return
    if coin == 0:   #初始化获取硬币数
        item_list = {}
        await verify()
        load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})   #获取会战币api
        if tvid == 0:
            tvid =load_index['user_info']['viewer_id']
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


#判定是否处于会战期间
    if load_index != 0:
        is_interval = load_index['clan_battle']['is_interval']
        if is_interval == 1:
            mode_change_open = load_index['clan_battle']['mode_change_limit_start_time']
            mode_change_open = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(mode_change_open))
            mode_change_limit = load_index['clan_battle']['mode_change_limit_time']
            mode_change_limit = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(mode_change_limit))
            msg = f'当前会战未开放，请在会战前一天初始化会战推送\n会战模式可切换时间{mode_change_open}-{mode_change_limit}'
            sw = 0
            for forward_group in forward_group_list:
                await bot.send_group_msg(group_id = forward_group,message = msg)
            return


#判定各BOSS圈数并获取预约表推送    
    num = 0
    for boss_info in res['boss_info']:
        lap_num = boss_info['lap_num']
        if lap_num != boss_status[num]:
            boss_status[num] = lap_num
            #msg += f'全新的{lap_num}周目{num+1}王来了！'
            push_list = pre_push[num]
            if push_list != []:     #预约后群内和行会内提醒
                chat_content = f'{lap_num}周目{num+1}王已被预约，请耐心等候！'
                try:
                    await verify()
                    await client.callapi('/clan/chat', {'clan_id': clan_id, 'type': 0, 'message': chat_content})
                except:
                    pass
                warn = ''
                for pu in push_list:
                    pu = pu.split('|')
                    uid = int(pu[0])
                    gid = int(pu[1])
                    atmsg = f'提醒：已到{lap_num}周目 {num+1} 王！请注意沟通上一尾刀~\n[CQ:at,qq={uid}]'
                    await bot.send_group_msg(group_id = gid,message = atmsg)
                pre_push[num] = []
        num += 1

#获取出刀记录并推送最新的出刀        
    if res != 0:
        history = reversed(res['damage_history'])   #从返回的出刀记录刀的状态
        clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
        clan_id = clan_info['clan']['detail']['clan_id']
        pre_clan_battle_id = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
        #print(res)
        if arrow == 0:
            for line in open(current_folder + "/Output.txt",encoding='utf-8'):
                if line != '':
                    line = line.split(',')
                    if line[0] != 'SL':
                        arrow = int(line[4])
                        print(arrow)
            #file.close()
        clan_battle_id = pre_clan_battle_id['clan_battle_id']
        for hst in history:
            if (arrow != 0) and (int(hst['history_id']) > int(arrow)):   #记录刀ID防止重复
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
                is_auto = hst['is_auto']
                if is_auto == 1:
                    is_auto_r = '自动刀'
                else:
                    is_auto_r = '手动刀'
    
                ifkill = ''     #击杀变成可读
                if kill == 1:
                    ifkill = '并击破'
                    #push = True
                
                for st in phase:
                    if lap >= st:
                        phases = st
                phases = phase[phases]                
                timeline = await client.callapi('/clan_battle/battle_log_list', {'clan_battle_id': clan_battle_id, 'order_num': boss, 'phases': [phases], 'report_types': [1], 'hide_same_units': 0, 'favorite_ids': [], 'sort_type': 3, 'page': 1})
                timeline_list = timeline['battle_list']
                #print(timeline_list)
                start_time = 0
                used_time = 0
                for tl in timeline_list:
                    if tl['battle_end_time'] == ctime:
                        blid1 = tl['battle_log_id']
                        tvid = tl['target_viewer_id']
                        print(blid1)
                        blid = await client.callapi('/clan_battle/timeline_report', {'target_viewer_id': tvid, 'clan_battle_id': clan_battle_id, 'battle_log_id': int(blid1)})
                        start_time = blid['start_remain_time']
                        used_time = blid['battle_time']
                if start_time == 90:
                    battle_type = f'初始刀{used_time}s'
                else:
                    battle_type = f'补偿刀{used_time}s'
                for st in side:
                    if lap >= st:
                        cur_side = st
                cur_side = side[cur_side]
                msg += f'[{cur_side}-{battle_type}]{name} 对 {lap} 周目 {boss} 王造成了 {damage} 伤害{ifkill}({is_auto_r})\n'
                output = f'{day},{hour},{minu},{seconds},{arrow},{name},{vid},{lap},{boss},{damage},{kill},{enemy_id},{clan_battle_id},{is_auto},{start_time},{used_time},'  #记录出刀，后面要用
                with open(current_folder+"/Output.txt","a",encoding='utf-8') as file:   
                    file.write(str(output)+'\n')
                    file.close()

#记录实战人数变动并推送
        change = False
        for num in range(0,5):  
            boss_info2 = await client.callapi('/clan_battle/boss_info', {'clan_id': clan_id, 'clan_battle_id': clan_battle_id, 'lap_num': boss_status[num], 'order_num': num+1}) 
            fnum = boss_info2['fighter_num']
            if in_game[num] != fnum:
                in_game[num] = fnum
                change = True
        if change == True:
            msg += f'当前实战人数发生变化:\n[{in_game[0]}][{in_game[1]}][{in_game[2]}][{in_game[3]}][{in_game[4]}]'

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
                        info = await bot.get_group_member_info(group_id=ev.group_id, user_id=pp1)
                        name = info['card'] or pp1
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
            pp2 = int(pp[1])
            
            try:
                info = await bot.get_group_member_info(group_id=pp2, user_id=pp1)
                name = info['card'] or pp1
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
    msg = '[查档线]:若参数为空，则输出10000名内各档档线；若有多个参数，请使用英文逗号隔开。新增按照关键词查档线。结算期间数据为空\n[初始化会战推送]:会战前一天输入这个，记得清空Output.txt内的内容，不要删除Output.txt\n[切换会战推送]:打开/关闭会战推送\n[会战预约(1/2/3/4/5)]:预约提醒\n[会战表]:查看所有预约\n[清空预约表]:(仅SU可用)\nsl + 关键ID:为玩家打上SL标记'
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
    #boss_ooo = [305700,302000,300602,304101,300100]
    #try:
    await bot.send(ev,'生成中...')
    ##第一部分
    
    for root_, dirs_, files_ in os.walk(img_file+'/bg'):
        bg = files_
    bgnum = random.randint(0, len(bg)-1)
    img = Image.open(img_file+'/bg/'+bg[bgnum])
    img = img.resize((1920,1080),Image.ANTIALIAS)
        
    front_img = Image.open(img_file+'/cbt.png')
    img.paste(front_img, (0,0),front_img) 
    draw = ImageDraw.Draw(img)
    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 40)
    await verify()
    
    load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
    clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
    clan_id = clan_info['clan']['detail']['clan_id']
    item_list = {}
    for item in load_index["item_list"]:
        item_list[item["id"]] = item["stock"]
    coin = item_list[90006]   
    res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
    clan_battle_id = res['clan_battle_id']
    clan_name = res['user_clan']['clan_name']
    draw.text((1340,50), f'{clan_name}', font=setFont, fill="#A020F0")
    rank = res['period_rank']
    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 25)
    draw.text((1340,170), f'排名：{rank}', font=setFont, fill="#A020F0")
    lap = res['lap_num']
    img_num = 0 
    for boss in res['boss_info']:
        boss_num = boss['order_num']
        boss_id = boss['enemy_id']
        boss_lap_num = boss['lap_num']
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
        if boss_lap_num - lap == 2:
            hp_color = "purple"
        elif boss_lap_num - lap == 1:
            hp_color = "pink"
    
        length = int((hp / mhp) * 1180)
        hp_bar = rounded_rectangle((length, 95), 10, hp_color)
        img.paste(hp_bar, (80, 40 + (boss_num - 1) * 142), hp_bar)
        try:    #晚点改
            try:
                img2 = R.img(f'priconne/unit/{boss_ooo[img_num]}.png').open()
            except:
                img2 = R.img(f'priconne/unit/icon_unit_100131.png').open()
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
        bg_width = 200
        stage_color = {
            1: 'green',
            4: 'yellow',
            11: 'blue',
            35: 'purple',
            45: 'red'
        }
        for st in side:
            if boss_lap_num >= st:
                cur_stage = st
        cur_stage = side[cur_stage]
        for st in stage_color:
            if boss_lap_num >= st:
                bg_color = st
        bg_color = stage_color[bg_color]
        bg = Image.new('RGBA', (bg_width, bg_height), bg_color)
        img.paste(bg, (500, 38+(boss_num-1)*142), bg)
        setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 25)
        draw.text((160, 40+(boss_num-1)*142), f'{format_number_with_commas(hp)}/{format_number_with_commas(mhp)}', font=setFont, fill="#FFFFFF")
        draw.text((500, 40+(boss_num-1)*142), f'{cur_stage}面 {boss_lap_num}周目', font=setFont, fill="#FFFFFF")

        
        
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
    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 20)
    last_rank = res2['last_total_ranking']
    draw.text((1320, 320), f'上期排名:{last_rank}', font=setFont, fill="#A020F0")
    all_battle_count = 0
    for members in res2['clan']['members']:
        vid = members['viewer_id']
        name = members['name']
        favor = members['favorite_unit']
        favorid = str(favor['id'])[:-2]
        stars = 3 if members['favorite_unit']['unit_rarity'] != 6 else 6
        try:
            img2 = R.img(f'priconne/unit/icon_unit_{favorid}{stars}1.png').open()
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
        setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 15)
        draw.text((1000,760), f'{today}日', font=setFont, fill="#A020F0")
        img3 = Image.new('RGB', (25, 17), "white")
        img4 = Image.new('RGB', (12, 17), "red")
        #img5 = Image.new('RGB', (25, 17), "green")
        time_sign = 0
        half_sign = 0
        sl_sign = 0
        for line in open(current_folder + "/Output.txt",encoding='utf-8'):
            if line != '':
                line = line.split(',')
                print(line[0])
                if line[0] == 'SL':
                    mode = 1
                    re_vid = int(line[2])
                    day = int(line[3])
                    hour = int(line[4])
                else:
                    mode = 2
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
                    re_clan_battle_id = int(line[12])
                    re_is_auto = int(line[13])
                    re_start_time = int(line[14])
                    re_battle_time = int(line[15])
                if_today = False
                if ((day == today and hour >= 5) or (day == today + 1 and hour < 5)) and (re_clan_battle_id == clan_battle_id) and mode == 2:
                    if_today = True
                if ((day == today and hour >= 5) or (day == today + 1 and hour < 5)) and mode == 1:
                    if_today = True
                
                
                if if_today == True and mode == 1 and int(vid) == int(re_vid):
                    sl_sign = 1
                
                if int(vid) == int(re_vid) and if_today == True and mode == 2:
                    if re_start_time == 90 and re_kill == 1:
                        if time_sign >= 1:
                            time_sign -= 1
                            half_sign -= 0.5
                            kill_acc += 0.5
                            continue
                        if re_battle_time <= 20 and re_battle_time != 0:
                            time_sign += 1
                        kill_acc += 0.5
                        half_sign += 0.5
                    elif re_start_time == 90 and re_kill == 0:
                        if time_sign >= 1:
                            kill_acc += 0.5
                            time_sign -= 1
                            half_sign -= 0.5
                            continue
                        kill_acc += 1
                    else:
                        kill_acc += 0.5
                        half_sign -= 0.5
                
        all_battle_count += kill_acc
        
        if kill_acc == 0:
            draw.text((132+149*width, 761+60*row), f'{name}', font=setFont, fill="#FF0000")
        elif 0< kill_acc < 3:
            draw.text((132+149*width, 761+60*row), f'{name}', font=setFont, fill="#FF00FF")
        elif kill_acc == 3:
            draw.text((132+149*width, 761+60*row), f'{name}', font=setFont, fill="#00FF00")
        #print(half_sign)
        width2 = 0
        kill_acc = kill_acc - half_sign
        
        while kill_acc-1 >=0:
            img.paste(img3, (130+int(149.5*width)+30*width2, 785+60*row))
            kill_acc -= 1
            width2 += 1
        while half_sign-0.5 >=0:
            img.paste(img4, (130+int(149.5*width)+30*width2, 785+60*row))
            half_sign -= 0.5
            width2 += 1
        #draw.text((132+149*width, 781+60*row), f'{kill_acc}', font=setFont, fill="#A020F0")
        if sl_sign == 1:
            draw.text((130+int(149.5*width), 785+60*row), f'SL', font=setFont, fill="black")
        width += 1
        if width == 6:
            width = 0
            row += 1    
    #file.close()
    count_m = len(res2['clan']['members'])*3        
    draw.text((1000,780), f'今日已出{all_battle_count}刀/{count_m}刀', font=setFont, fill="#A020F0")
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
                msg = f'[{day}日{hour:02}:{minu:02}]{name} 对 {lap} 周目 {boss} 王造成了 {damage} 伤害{ifkill}'
                if kill == 1:
                    draw.text((1320, 385+(order*15)), f'{msg}', font=setFont, fill="black")
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
                                img2 = R.img(f'priconne/unit/icon_unit_{favorid}{stars}1.png').open()
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

@sv.on_prefix('抓人')
async def get_battle_status(bot,ev):
    msg = ev.message.extract_plain_text().strip()
    if msg != '':
        today = int(msg)
    else:
        todayt = time.localtime()
        hourh = todayt[3]
        today = 0
        if hourh < 5:
            today = todayt[2]-1
        else:
            today = todayt[2]      
    await verify()
    load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
    clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
    clan_id = clan_info['clan']['detail']['clan_id']
    item_list = {}
    for item in load_index["item_list"]:
        item_list[item["id"]] = item["stock"]
    coin = item_list[90006]   
    res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
    clan_battle_id = res['clan_battle_id']
    day_sign = 0
    num = 0
    battle_history_list = []
    while(day_sign == 0):
        num += 1
        timeline = await client.callapi('/clan_battle/battle_log_list', {'clan_battle_id': clan_battle_id, 'order_num': 0, 'phases': [1,2,3,4,5], 'report_types': [1], 'hide_same_units': 0, 'favorite_ids': [], 'sort_type': 3, 'page': num})
        for tl in timeline['battle_list']:
            tvid = tl['target_viewer_id']
            log_id = tl['battle_log_id']
            ordern_num = tl['order_num']
            lap_num = tl['lap_num']
            battle_end_time = tl['battle_end_time']
            usrname = tl['user_name']
            hr = time.localtime(battle_end_time)
            day = hr[2]
            hour = hr[3]
            if (day == today and hour >= 5) or (day == today + 1 and hour < 5):
                battle_history_list.append([tvid,log_id,usrname])
            elif (day < today):
                day_sign = 1
    for log in battle_history_list:
        tvid = log[0]
        log_id = log[1]
        usrname = log[2]
        blid = await client.callapi('/clan_battle/timeline_report', {'target_viewer_id': tvid, 'clan_battle_id': clan_battle_id, 'battle_log_id': int(log_id)})
        start_time = blid['start_remain_time']
        used_time = blid['battle_time']
        for tl in blid['timeline']:
            if tl['is_battle_finish'] == 1:
                remain_time = tl['remain_time']
                if remain_time != 0:
                    kill = 1
                else:
                    kill = 0
        log.append(start_time)
        log.append(used_time)
        log.append(kill)
        #print(blid)
    res2 = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 1})
    #lack_list = []
    msg = ''
    for members in res2['clan']['members']:
        vid = members['viewer_id']
        name = members['name']
        time_sign = 0
        half_sign = 0
        kill_acc = 0
        for log in battle_history_list:
            if log[0] == vid:
                start_time = log[3]
                used_time = log[4]
                kill = log[5]
                if start_time == 90 and kill == 1:
                    if time_sign >= 1:
                        time_sign -= 1
                        half_sign -= 0.5
                        kill_acc += 0.5
                        continue
                    if used_time <= 20 and used_time != 0:
                        time_sign += 1
                    kill_acc += 0.5
                    half_sign += 0.5
                elif start_time == 90 and kill == 0:
                    if time_sign >= 1:
                        kill_acc += 0.5
                        time_sign -= 1
                        half_sign -= 0.5
                        continue
                    kill_acc += 1
                else:
                    kill_acc += 0.5
                    half_sign -= 0.5
        if kill_acc < 3:
            msg += f'{name}缺少{3-kill_acc}刀\n'
    if msg != '':
        await bot.send(ev,msg)
    
@sv.on_prefix('sl')     
async def sl(bot,ev):
    usrname = ev.message.extract_plain_text().strip()
    if usrname == '':
        # pp1 = ev.user_id
        # try:
        #     info = await bot.get_group_member_info(group_id=ev.group_id, user_id=pp1)
        #     usrname = info['card'] or pp1
        # except CQHttpError as e:
        #     print('error name')
        #     pass      
        await bot.send(ev,'由于不进行绑定，请输入一个游戏内的ID辨识(关键词搜索)')
        return
    else:
        #try:
        await verify()
        res2 = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 1})
        search_sign = 0
        vid0 = 0
        for members in res2['clan']['members']:
            vid = members['viewer_id']
            name = str(members['name'])
            
            if (usrname == name) or (usrname in name):
                usrname = name
                todayt = time.localtime()
                hourh = todayt[3]
                monm = todayt[1]
                today = 0
                if hourh < 5:
                    today = todayt[2]-1
                else:
                    today = todayt[2]
                for line in open(current_folder + "/Output.txt",encoding='utf-8'):
                    if line != '':
                        line = line.split(',')
                        if line[0] == 'SL':
                            name2 = line[1]
                            vid0 = int(line[2])
                            day = int(line[3])
                            hour = int(line[4])
                            minu = int(line[5])
                            seconds = int(line[6])
                            mon = line[7]
                            if (name2 == name) and (((day == today and hour >= 5) or (day == today + 1 and hour < 5))):
                                await bot.send(ev,f'({name})已于{hour}:{minu}进行过SL操作！')
                                return
                vid0 = vid
                search_sign = 1
                break
        if search_sign == 1:
            real_time = time.localtime()
            mon = real_time[1]
            day = real_time[2]  #垃圾代码
            hour = real_time[3]
            minu = real_time[4]
            seconds = real_time[5]
            output = f'SL,{usrname},{vid0},{day},{hour},{minu},{seconds},{mon},'
            with open(current_folder+"/Output.txt","a",encoding='utf-8') as file:   
                file.write(str(output)+'\n')
                file.close()
            await bot.send(ev,f'{name}({vid0})已上报SL')
        else:
            await bot.send(ev,'没有找到这个ID，请确认')
            return
        # except:
        #     await bot.send(ev,'发生连接错误，请重试')
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





#查档线等待修改和上传图片
RANK_LST = [1,4,11,21,51,201,601,1201,2801,5001,10001,15001,25001,40001,60001]



@sv.on_prefix('查档线')     #从游戏内获取数据，无数据时返回空
async def query_line(bot,ev):
    goal = ev.message.extract_plain_text().strip()
    await verify()
    try:
        load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
    except:
        load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
    try:
        goal_list = []
        if re.match("^[0-9,]+$", goal):
            print('mode1')
            rank_mode = 1
            if ',' in goal:
                goal_list = goal.split(',')
            else:
                goal_list.append(goal)
        elif goal == '':
            goal_list = [1,4,11,21,51,201,601,1201,2801,5001]
            await bot.send(ev,'获取数据时间较长，请稍候')
        else:
            rank_mode = 2
            goal_list = []
            await bot.send(ev,f'正在搜索行会关键词{goal}')
            clan_name_search =  await client.callapi('/clan/search_clan', {'clan_name': goal, 'join_condition': 1, 'member_condition_range': 0, 'activity': 0, 'clan_battle_mode': 0})
            clan_list = ''
            for clan in clan_name_search['list']:
                clan_name = clan['clan_name']
                clan_list += f'[{clan_name}]'
            clan_num = len(clan_name_search['list'])
            await bot.send(ev,f'找到{clan_num}个与关键词相关行会,超过5个的将不会查询，请精确化关键词\n{clan_list}')
            clan_num = 0
            for clan in clan_name_search['list']:
                
                if clan_num <= 4:
                    clan_id = clan['clan_id']
                    print(clan_id)
                    if clan_id == 0:
                        break
                    clan_most_info = await client.callapi('/clan/others_info', {'clan_id': clan_id})
                    clan_most_info = clan_most_info['clan']['detail']['current_period_ranking']
                    if clan_most_info == 0:
                        continue
                    goal_list.append(clan_most_info)
                    clan_num += 1

                else:
                    break
                    #goal_list.append(clan_most_info)
                    #print(goal_list)
        if goal_list == []:
            await bot.send(ev,'无法获取排名，可能是官方正在结算，请等待结算后使用本功能')
            return
        width2 = 500*len(goal_list)
        img4 = Image.new('RGB', (1000, width2), (255, 255, 255))    
        all_num = 0
        print(len(goal_list))
        for goal in goal_list:
            goal = int(goal)
            item_list = {}
            for item in load_index["item_list"]:
                item_list[item["id"]] = item["stock"]
            coin = item_list[90006]   
            load_index2 = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 1})
            clan_name = load_index2
            clan_id = clan_name['clan']['detail']['clan_id']
            res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
            clan_battle_id = res['clan_battle_id']
    
            page = int((goal-1)/10)
            indi = goal%10
            if indi == 0:
                indi = 10
            
            page_info = await client.callapi('/clan_battle/period_ranking', {'clan_id': clan_id, 'clan_battle_id': clan_battle_id, 'period': 1, 'month': 0, 'page': page, 'is_my_clan': 0, 'is_first': 1})
            if page_info['period_ranking'] == []:
                await bot.send(ev,'当前会战排名正在结算，无法获取数据，请等待官方结算完成后再使用本功能~')
                return
            #print(page_info)
            num = 0
            
            lap = 0
            boss = 0
            
            stage = [207300000,859700000,4430900000,8113900000,999999999999]
            l1 = [[7200000,9600000,13000000,16800000,22500000],[9600000,12800000,18000000,22800000,30000000],[14000000,18000000,28800000,36000000,52000000],[59500000,63000000,74000000,79800000,92000000],[297500000,315000000,351500000,380000000,440000000]]
            lp = [3,10,34,44,999]
            
            for rank in page_info['period_ranking']:
                num += 1
                if num == indi:
                    rank_num = rank['rank']
                    dmg = rank['damage']
                    mem = rank['member_num']
                    name = rank['clan_name']
                    lvid = rank['leader_viewer_id']
                    lname = rank['leader_name']
                    lunit = rank['leader_favorite_unit']['id']
                    grank = rank['grade_rank']
                    
                    
                    for stag in stage:
                        lap += 1
                        if dmg <= stag:
                            dmg_left = dmg - stage[lap-2]
                            break
                    
                    llps = 0
                    while(dmg_left > 0):
                        boss = 0
                        for i in l1[lap-1]:
                            if dmg_left - i > 0:
                                boss += 1 
                                dmg_left -= i
                            else:
                                final_dmg = dmg_left
                                final_dmgg = i
                                dmg_left = -1
                                break
                        llps += 1
                        #print(1)
                    final_lap = lp[lap-2] + llps
                    progress = (float(final_dmg/i)*100)
                    progress = round(progress, 2)
                    msg = f'当前第 {lap} 阶段 | 第 {final_lap} 周目 {boss+1} 王 | 进度 {progress}%'
                    print(msg)
                    
                    R_n = 0
                    for RA in RANK_LST:
                        if rank_num < RA:
                            prev_r = RA
                            next_r = RANK_LST[R_n-1]
                            break
                        R_n += 1
                    img_file2 = '/data_new/Hoshino/res/img/priconne/unit'
                    icon_unit = rank['leader_favorite_unit']['id']
                    stars = rank['leader_favorite_unit']['unit_rarity']
                    st = 1 if stars < 3 else 3
                    st = st if st != 6 else 6
                    chara_id = str(icon_unit)[:-2]           
         ############################################           
                    clan_ids = ''
                    clan_idsss = 0
                    for n in range(0,6):
                        clan_info = await client.callapi('/clan/search_clan', {'clan_name': name, 'join_condition': 1, 'member_condition_range': 0, 'activity': 0, 'clan_battle_mode': 0})
                        #print(clan_info)
                        try:
                            clan_ids = clan_info['list']
                            for clan_idss in clan_ids:
                                clan_lid = clan_idss['leader_viewer_id']
                                if lvid == clan_lid:
                                    clan_idsss = clan_idss['clan_id']
                                    break
                        except:
                            result = f'获取行会信息失败{n}/n'
                            print(result)
                            
                            pass
                    img = Image.open(img_file + f'//bkg.png')
                    draw = ImageDraw.Draw(img)            
                    if clan_idsss == 0:
                        info_msg = f'获取行会信息失败(该行会未开放搜索或同名过多)'
                        setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 15)
                        draw.text((350,250), f'{info_msg}', font=setFont, fill="#4A515A")
                    else:
                        clan_most_info = await client.callapi('/clan/others_info', {'clan_id': clan_idsss})
                        clan_member = clan_most_info['clan']['members']
                        descrip = clan_most_info['clan']['detail']['description']
                        join_con = clan_most_info['clan']['detail']['join_condition']
        
                    
                    wi = 0
                    de = 0
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 15)
                    try:
                        for member in clan_member:
                            vid = member['viewer_id']
                            usr_name = member['name']
                            level = member['level']
                            lg_time = member['last_login_time']
                            power = member['total_power']
                            #clan_point = member['clan_point']
                            time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(lg_time))
                            draw.text((350+wi*120,250+de*20), f'{usr_name}', font=setFont, fill="#4A515A")
                            wi += 1
                            if wi >= 5:
                                wi = 0
                                de += 1
                    except:
                        pass
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 20)
                    draw.text((20,220), f'当前位次: {rank_num}位', font=setFont, fill="#4A515A")
                    draw.text((20,240), f'会长: {lname}', font=setFont, fill="#4A515A")
                    draw.text((20,260), f'VID: [{lvid}]', font=setFont, fill="#4A515A")
                    draw.text((20,280), f'上期位次: {grank}位', font=setFont, fill="#4A515A")
                    try:
                        draw.text((20,180), f'{descrip}', font=setFont, fill="#4A515A")
                    except:
                        pass
                    draw.text((350,220), msg, font=setFont, fill="#4A515A")
                    
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 30)
                    draw.text((750,75), f'{dmg}', font=setFont, fill="#4A515A")
                    draw.text((850,135), f'{mem}/30', font=setFont, fill="#4A515A")
                    draw.text((50,440), f'{prev_r}位', font=setFont, fill="#4A515A")
                    draw.text((850,440), f'{next_r}位', font=setFont, fill="#4A515A")
                    
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 40)
                    draw.text((500,15), f'{name}', font=setFont, fill="#4A515A")
                    
                    try:
                            
                        img3 = R.img(f'priconne/unit/icon_unit_{chara_id}{st}1.png').open()
                        img3 = img3.resize((160, 160))
                        img.paste(img3, (17,17))            
                    except:
                        pass
                    
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 50)
                    #draw.text((270,10), f'--位', font=setFont, fill="#CC9900")
                    
                    if len(goal_list) != 1:
                        
                        
                        img4.paste(img, (0,500*all_num))
                    
                    
                        
                    all_num+=1    
                    
        if len(goal_list) != 1:
            imgq = pic2b64(img4)
            imgq = MessageSegment.image(imgq)
        else:
            imgq = pic2b64(img)
            imgq = MessageSegment.image(imgq)        
        await bot.send(ev,imgq)
    except Exception as e:
        print(e)
        await bot.send(ev,'获取数据时发生错误，请重试')
        pass
