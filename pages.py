#!/usr/bin/python
# encoding: utf-8
#
# Copyright (c) 2010 shinysky
# See LICENSE for details.

import sys, traceback
import string
import time, calendar

from twisted.conch.insults import insults

import tweepy
import simplejson as json

import pwdchecker
import utils
import consts

class registerPage:
    '''注册新用户
    1. 提示输入用户名([0-9a-zA-Z]+)
    2. 验证用户名是否已存在
    3. 提示输入密码(string.printable[:-5])
    4. 提示重新输入密码
    5. 验证密码是否相同
    6. 保存name:pass到数据库
    7. 提示重新登录
    '''

    def __init__(self, dbcursor, terminal):
        self.dbcursor = dbcursor
        self.terminal = terminal
        self.buffer = []
        # i know, this is stupid!
        self.accept = False
        self.echoback = True
        self.loseConn = False
        self.verify = False

        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.showPrompt_username()

    def showPrompt_username(self):
        '''registering procedure begins here
        '''
        #TODO 提示用户username/password的可用字符
        self.terminal.write('\r\n')
        self.terminal.write('Step 1: Input your username: ')
        self.buffer = []
        self.echoback = True
        self.accept = True

    def showPrompt_pwd(self):
        self.terminal.write('\r\n')
        self.terminal.write('Step 2: Input your password: ')
        self.buffer = []
        self.echoback = False
        self.accept = True

    def showPrompt_verify(self):
        self.terminal.write('\r\n')
        self.terminal.write('Step 3: Verify your password: ')
        self.buffer = []
        self.echoback = False
        self.accept = True
    
    def showPrompt_relogin(self):
        self.accept = True
        self.loseConn = True
        self.terminal.write('\r\n')
        self.terminal.write('Press any key to disconnect...')

    def showPrompt_userexist(self):
        self.terminal.eraseLine()
        self.terminal.cursorHome()
        self.terminal.write('\x1b[1;31mThis username is already taken, try another one.\x1b[0m')
        self.showPrompt_username()

    def showPrompt_succeed(self):
        self.terminal.write('\r\n\r\n')
        self.terminal.write('Congratulations! You just signed up successfully!\r\n')
        self.terminal.write('Now please disconnect and login again to enjoy Tw!term!\r\n')
        self.showPrompt_relogin()

    def showPrompt_fail(self):
        self.terminal.write('\r\n\r\n')
        self.terminal.write('\x1b[1;31mThe two passwords you input does not match!\x1b[0m')
        self.showPrompt_relogin()
        
    def keystrokeReceived(self, keyID, modifier):
        '''处理键盘事件'''
        if not self.accept:
            return

        if self.loseConn:
            self.terminal.loseConnection()
            return

        #TODO 长度限制
        # username
        if self.echoback:
            if keyID in string.ascii_letters or keyID in string.digits:
                self.terminal.write(keyID)
                self.buffer.append(keyID)
        else: # password
            if str(keyID) in string.printable[:-5]:
                self.terminal.write('*')
                self.buffer.append(keyID)

        if keyID == self.terminal.BACKSPACE:
            if len(self.buffer) > 0:
                del self.buffer[-1]
                self.terminal.cursorBackward()
                self.terminal.write(' ')
                self.terminal.cursorBackward()
        elif keyID == '\r':
            if len(self.buffer) > 0:
                if self.echoback:
                    self.user = ''.join(self.buffer)
                    self.user = self.user.lower()
                    self.accept = False
                    # 验证用户名是否可用
                    self.dbcursor.execute('select name from sysusers where name=?', (self.user,))
                    u = self.dbcursor.fetchone()
                    if u:
                        self.showPrompt_userexist()
                    else:
                        self.showPrompt_pwd()
                elif not self.verify:
                    self.pwd = ''.join(self.buffer)
                    self.accept = False
                    self.showPrompt_verify()
                    self.verify = True
                else:
                    self.pwd2 = ''.join(self.buffer)
                    self.accept = False
                    if self.pwd == self.pwd2:
                        self.dbcursor.execute('insert into sysusers values(?,?,?)',
                                (self.user,
                                    pwdchecker.hash(self.user, self.pwd, ''),
                                    None))
                        self.showPrompt_succeed()
                    else:
                        self.showPrompt_fail()

            else:
                pass
        else:
            pass

#========================================================
class bindingPage:
    '''负责: 绑定账号.
    1. 提示用户打开一个URL来获取PIN码
    2. 提示用户输入PIN码(7位数字)
    3. 使用PIN码和twitter.com交换token
    4. 使用获得的token尝试获取绑定用户的信息
    5. 成功则绑定成功, 提示用户重登录
    6. 失败则绑定失败, 提示用户重连接来重试
    '''

    def __init__(self, user, dbcursor, terminal, pcallback = None):
        self.user = user
        self.dbcursor = dbcursor
        self.terminal = terminal
        self.pcallback = pcallback
        self.accept = False
        self.loseConn = False
        self.buffer = []
        self.showPrompt()

    def showPrompt(self):
        '''binding procedure begins here
        '''
        #OAuth
        self.tempauth = tweepy.OAuthHandler(consts.CONSUMER_KEY, consts.CONSUMER_SECRET)
        # Redirect user to Twitter to authorize
        # Ask for PIN code
        url = self.tempauth.get_authorization_url(True)
        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.terminal.write('Step 1: Open this URL with your browser to approve this app: \r\n%s' % url)
        self.terminal.nextLine()
        self.terminal.write('Step 2: Input 7 digit PIN you get from twitter.com:')
        self.buffer = []
        self.accept = True
        self.loseConn = False
    
    def exchangeToken(self, PIN):
        '''binding procedure step2
        '''
        self.accept = False
        try:
            # Get access token
            token = self.tempauth.get_access_token(PIN)
            api = tweepy.API(self.tempauth)
            profile = api.verify_credentials()
            profile = json.loads(profile)
            utils.saveTwitterUser(self.dbcursor, profile)
            id = profile['id']
            # already exist?
            self.dbcursor.execute('select owner from bindings where id=?',
                    (id,))
            n = self.dbcursor.fetchone()
            if n:
                raise Exception('This twitter account is already binded!')
            else:
                self.dbcursor.execute('insert into bindings values(?,?,?,?,?)',
                        (id,
                            self.user,
                            token.key,
                            token.secret,
                            None))
                # create new table after binding procedure
                # tweet table
                tweettablename = 'x%d' % id
                # tag: home, mentions, retweet, favorited, read
                self.dbcursor.execute('''create table %s (
                        id integer primary key,
                        tag integer,
                        fromid integer,
                        createtime text,
                        source text,
                        content text,
                        replytostatusid integer,
                        other text)''' % tweettablename)
                # direct message table
                dmtablename = 'd%d' % id
                # tag:  read or not
                self.dbcursor.execute('''create table %s (
                        id integer primary key,
                        tag integer,
                        fromid integer,
                        toid integer,
                        createtime text,
                        content text)''' % dmtablename)
                #TODO unbinding will drop these tables
                self.terminal.write('\r\n\r\n')
                self.terminal.write('Congratulations!\r\n')
                self.terminal.write('You just binded a twitter account to your account successfully.\r\n')
                self.terminal.write('Now please disconnect and login again to enjoy Tw!term!\r\n')
        except Exception, e:
            traceback.print_exc(file=sys.stdout)
            self.terminal.write('\r\n\r\n')
            self.terminal.write('Something is wrong, relogin to try again:\r\n')
            self.terminal.write('\x1b[1;31m%s\x1b[0m\r\n' % e.message)

        self.accept = True
        self.loseConn = True
        self.terminal.write('Press any key to disconnect...')

    def keystrokeReceived(self, keyID, modifier):
        '''处理键盘事件'''
        if not self.accept:
            return

        if self.loseConn:
            self.terminal.loseConnection()
            return

        if keyID in string.digits:
            self.terminal.write(keyID)
            self.buffer.append(keyID)
        elif keyID == self.terminal.BACKSPACE:
            if len(self.buffer) > 0:
                del self.buffer[-1]
                self.terminal.cursorBackward()
                self.terminal.write(' ')
                self.terminal.cursorBackward()
        elif keyID == '\r':
            if self.pcallback and (not self.buffer):
                self.pcallback()
            if len(self.buffer) == 7:
                self.exchangeToken(''.join(self.buffer))
            else:
                pass
        else:
            pass

#========================================================
class mainListPage:
    '''main list for selection'''
    def __init__(self, apis, user, tusers, dbcursor, terminal):
        self.apis = apis
        self.user = user
        self.tusers = tusers
        self.dbcursor = dbcursor
        self.terminal = terminal
        self.cursor = consts.CURSOR
        self.cursorX, self.cursorY = 0, 0
        self.curpage = None
        self.show()
        utils.moveCursorTo(self.terminal, self.cursor, 2, 0)

    def show(self):
        '''show the list'''
        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        for i in xrange(len(self.tusers)):
            self.terminal.write('''\x1b[1;37m    ● (%d)%s\x1b[0m\r\n''' % (i+1, self.tusers[i][1].encode('utf-8')))
        self.terminal.write('''\
    \x1b[1;33m● (H)Help\x1b[0m
    \x1b[1;33m● (A)About\x1b[0m
    \x1b[1;32m● (N)New binding\x1b[0m
    \x1b[1;31m● (B)Goodbye!\x1b[0m''')

    def callback(self, *args):
        '''called by sub-pages'''
        del self.curpage
        self.curpage = None
        self.show()
        utils.moveCursorTo(self.terminal, self.cursor, self.cursorX, self.cursorY)

    def keystrokeReceived(self, keyID, modifier):
        '''处理键盘事件'''
        if self.curpage:
            self.curpage.keystrokeReceived(keyID, modifier)
            return

        if keyID == self.terminal.UP_ARROW or keyID == '\x1b[OA' or keyID == 'k':
            if self.terminal.cursorPos.y > 0:
                utils.cursorUp(self.terminal, self.cursor)
        elif keyID == self.terminal.DOWN_ARROW or keyID == '\x1b[OB' or keyID == 'j':
            if self.terminal.cursorPos.y < len(self.tusers) + 3:
                utils.cursorDown(self.terminal, self.cursor)
        #elif keyID == self.terminal.LEFT_ARROW or keyID == '\x1b[OD' or keyID == 'e' or keyID == 'q':
        #    utils.moveCursorTo(self.terminal, self.cursor, 2, len(self.tusers)+3)
        elif keyID == self.terminal.RIGHT_ARROW or keyID == '\x1b[OC' or keyID == '\r':
            i = self.terminal.cursorPos.y
            if i >= 0 and i < len(self.tusers):
                self.cursorX = self.terminal.cursorPos.x
                self.cursorY = self.terminal.cursorPos.y
                self.curpage = timelinePage(self.apis[self.tusers[i][0]],
                        self.user, self.tusers[i],
                        self.dbcursor, self.terminal,
                        self.callback)
            elif i == len(self.tusers) + 2:
                self.curpage = bindingPage(self.user, self.dbcursor, self.terminal, self.callback)
            elif i == len(self.tusers) + 3:
                self.terminal.loseConnection()
                return
            else:
                #TODO the other options
                pass

#========================================================
class timelinePage:
    '''timelines'''
    def __init__(self, api, user, tuser, dbcursor, terminal, pcallback):
        self.api = api
        self.user = user
        self.tuser = tuser
        self.dbcursor = dbcursor
        self.terminal = terminal
        self.pcallback = pcallback
        self.cursor = consts.CURSOR
        self.cursorX, self.cursorY = 0, 0
        self.curpage = None

        self.titles = ('Home','Mentions','Direct Messages','My Tweets','Favorites')

        self.show()
        utils.moveCursorTo(self.terminal, self.cursor, 2, 0)

    def show(self):
        '''show the list'''
        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.terminal.write('''\x1b[1;37m\
    ● (H)Home
    ● (M)Mentions
    ● (D)Direct Messages
    ● (T)My Tweets
    ● (F)Favorites
    ● (L)Lists\x1b[0m''')

    def callback(self, *args):
        '''called by sub-pages
        @ivar param type:dict modified tweets' id(read or favorited) and tags
        @ivar param type:bool isDM
        '''
        del self.curpage
        self.curpage = None
        self.show()
        utils.moveCursorTo(self.terminal, self.cursor, self.cursorX, self.cursorY)
        #TODO write back read tweets
        tablename = 'x%d' % self.tuser[0]
        if args[1]:#isDM
            tablename = 'd%d' % self.tuser[0]
        for k,v in args[0].items():
            self.dbcursor.execute('update %s set tag = ? where id = ?' % tablename,
                    (v, k))

    def keystrokeReceived(self, keyID, modifier):
        '''处理键盘事件'''
        if self.curpage:
            self.curpage.keystrokeReceived(keyID, modifier)
            return

        if keyID == self.terminal.UP_ARROW or keyID == '\x1b[OA' or keyID == 'k':
            if self.terminal.cursorPos.y > 0:
                utils.cursorUp(self.terminal, self.cursor)
        elif keyID == self.terminal.DOWN_ARROW or keyID == '\x1b[OB' or keyID == 'j':
            if self.terminal.cursorPos.y < 5:
                utils.cursorDown(self.terminal, self.cursor)
        elif keyID == self.terminal.LEFT_ARROW or keyID == '\x1b[OD' or keyID == 'e' or keyID == 'q':
            self.pcallback()
        elif keyID == self.terminal.RIGHT_ARROW or keyID == '\x1b[OC' or keyID == '\r':
            i = self.terminal.cursorPos.y
            if i in (0,1,3,4):
                self.cursorX = self.terminal.cursorPos.x
                self.cursorY = self.terminal.cursorPos.y
                self.dbcursor.execute('select * from {0} \
                        inner join twitterusers \
                        on {0}.fromid = twitterusers.id \
                        order by {0}.id desc'.format('x%d' % self.tuser[0]))
                tweets = self.dbcursor.fetchall()
                temptweets = []
                if i == 0:
                    temptweets = [t for t in tweets if (t[1] & utils.TagHome)]
                elif i == 1:
                    temptweets = [t for t in tweets if (t[1] & utils.TagMentions)]
                elif i == 3:
                    temptweets = [t for t in tweets if t[2] == self.tuser[0]]
                elif i == 4:
                    temptweets = [t for t in tweets if (t[1] & utils.TagFavorited)]

                self.curpage = tweetListPage(self.api, self.titles[i], self.user, self.tuser,
                        temptweets, self.dbcursor, self.terminal, self.callback)
            elif i == 2:
                #TODO direct message page
                self.cursorX = self.terminal.cursorPos.x
                self.cursorY = self.terminal.cursorPos.y
                self.dbcursor.execute('select * from ({0} \
                        inner join twitterusers F\
                        on {0}.fromid = F.id) \
                        inner join twitterusers S \
                        on {0}.toid = S.id\
                        order by {0}.id desc'.format('d%d' % self.tuser[0]))
                tweets = self.dbcursor.fetchall()
                self.curpage = tweetListPage(self.api, self.titles[i], self.user, self.tuser,
                        tweets, self.dbcursor, self.terminal, self.callback, isDM = True)
            else:
                #TODO the other options
                pass

#========================================================
class tweetListPage:
    '''tweet list'''
    def __init__(self, api, title, user, tuser, tweets, dbcursor,
            terminal, pcallback, isDM = False):
        self.api = api
        self.title = title
        self.user = user
        self.tuser = tuser
        self.tweets = tweets
        self.dbcursor = dbcursor
        self.terminal = terminal
        self.pcallback = pcallback
        self.isDM = isDM

        self.cursor = consts.CURSOR
        self.cursorX, self.cursorY = 0, 0
        self.curpage = None

        self.modtweets = {}

        # 总页数
        self.maxpage = (len(self.tweets)-1)/20 + 1
        self.templist = None
        self.pagecursor = 0
        self.show()

    def show(self):
        '''show the list'''
        self.terminal.eraseDisplay()
        #TODO 汉字在终端上占2位, format计算时会算成三位(unicode编码长度)
        head = '\x1b[1;33;44m@{0:<14}{1:^50}{2:>15}\r\n'.format(self.tuser[1], self.title, 'Tw!term')\
                + '\x1b[0m\x1b[1;32m{0:^92}\r\n'.format('发推[p] 回复[r] 发信[m] 标记[g] 搜索[/] 求助[h]')\
                + '\x1b[1;33;44m   {0:<17} {1:<63}\r\n'.format('作者', '状态')
        self.terminal.cursorHome()
        self.terminal.write(head)
        foot = '\x1b[1;33;44m{0:80}\x1b[0m'.format(\
                '')
        utils.setCursorPosition(self.terminal, 0, self.terminal.termSize.y-1)
        self.terminal.write(foot)
        self.showPage()
        utils.moveCursorTo(self.terminal, self.cursor, 0, 3)

    def showPage(self):
        # clean page
        for i in xrange(3, 23):
            utils.setCursorPosition(self.terminal, 0, i)
            self.terminal.eraseLine()
        utils.setCursorPosition(self.terminal, 0, 3)
        self.terminal.write(self.getTweetListPageStr())

    def getTweetListPageStr(self):
        '''return result page string for terminal to display
        '''
        #TODO 汉字在终端上占2位, format计算时会算成三位(unicode编码长度)
        self.templist = self.tweets[20*self.pagecursor:20*self.pagecursor+20]

        #tweet[5].encode('utf-8').replace('\r',' ').replace('\n',' ')[:72]
        index = 10
        if self.isDM:
            index = 8
        content = '\r\n'.join([' {0:<2}{1}{2:<15} {3}\x1b[0m'.format(\
                (tweet[1]&utils.TagFavorited) and '\x1b[1;33m★\x1b[0m' or '  ',
                (tweet[1]&utils.TagRead) and '\x1b[0m' or '\x1b[1;33m',
                tweet[index].encode('utf-8'),
                utils.split(tweet[5], 61).encode('utf-8')) for tweet in self.templist])
        return content

    def callback(self, *args):
        '''called by sub-pages'''
        del self.curpage
        self.curpage = None
        if len(args) > 0:
            self.pagecursor = args[0] / 20
            self.show()
            utils.moveCursorTo(self.terminal, self.cursor, 0, args[0]%20 + 3)
        else:
            self.show()
            utils.moveCursorTo(self.terminal, self.cursor, self.cursorX, self.cursorY)

    def keystrokeReceived(self, keyID, modifier):
        '''处理键盘事件'''
        if self.curpage:
            self.curpage.keystrokeReceived(keyID, modifier)
            return

        if keyID == self.terminal.UP_ARROW or keyID == '\x1b[OA' or keyID == 'k':
            if self.terminal.cursorPos.y > 3:
                utils.cursorUp(self.terminal, self.cursor)
            elif self.terminal.cursorPos.y == 3 and self.pagecursor > 0:
                self.pagecursor -= 1
                self.showPage()
                utils.moveCursorTo(self.terminal, self.cursor, 0, self.terminal.termSize.y-2)
        elif keyID == self.terminal.DOWN_ARROW or keyID == '\x1b[OB' or keyID == 'j':
            if self.terminal.cursorPos.y < len(self.templist)+2:
                utils.cursorDown(self.terminal, self.cursor)
            elif self.terminal.cursorPos.y == self.terminal.termSize.y-2\
                    and self.pagecursor < self.maxpage-1:
                self.pagecursor += 1
                self.showPage()
                utils.moveCursorTo(self.terminal, self.cursor, 0, 3)
        elif keyID == self.terminal.LEFT_ARROW or keyID == '\x1b[OD' or keyID == 'e' or keyID == 'q':
            self.pcallback(self.modtweets, self.isDM)
        elif keyID == self.terminal.RIGHT_ARROW or keyID == '\x1b[OC' or keyID == '\r':
            i = self.terminal.cursorPos.y
            if i >= 3 and i <= len(self.templist)+2:
                self.cursorX = self.terminal.cursorPos.x
                self.cursorY = self.terminal.cursorPos.y
                if self.isDM:
                    self.curpage = dmPage(self.api,
                            self.user, self.tuser,
                            self.dbcursor, self.terminal,
                            self.tweets, self.pagecursor*20+(i-3),
                            self.modtweets,
                            self.callback)
                else:
                    self.curpage = tweetPage(self.api,
                            self.user, self.tuser,
                            self.dbcursor, self.terminal,
                            self.tweets, self.pagecursor*20+(i-3),
                            self.modtweets,
                            self.callback)
        elif keyID == self.terminal.PGUP:
            if self.pagecursor > 0:
                self.pagecursor -= 1
                self.showPage()
                utils.moveCursorTo(self.terminal, self.cursor, 0, 3)
        elif keyID == ' ' or keyID == self.terminal.PGDN:
            if self.pagecursor < self.maxpage - 1:
                self.pagecursor += 1
                self.showPage()
                utils.moveCursorTo(self.terminal, self.cursor, 0, 3)
        elif keyID == self.terminal.HOME or keyID == '\x1b[7~':
            # 显示第一页
            self.pagecursor = 0
            self.showPage()
            utils.moveCursorTo(self.terminal, self.cursor, 0, 3)
        elif keyID == self.terminal.END or keyID == '\x1b[8~':
            # 显示最后一页
            self.pagecursor = self.maxpage-1
            self.showPage()
            i = len(self.tweets)%20
            if i == 0: i = 20
            utils.moveCursorTo(self.terminal, self.cursor, 0, i+2)
        elif keyID == 'p':
            self.cursorX = self.terminal.cursorPos.x
            self.cursorY = self.terminal.cursorPos.y
            self.curpage = postPage(self.api, self.terminal, self.callback)
        elif keyID == 'g':#favorise
            i = self.terminal.cursorPos.y
            if i >= 3 and i <= len(self.templist)+2:
                tweet = list(self.tweets[self.pagecursor*20+(i-3)])
                tweet[1] = tweet[1] ^ utils.TagFavorited
                self.tweets[self.pagecursor*20+(i-3)] = tuple(tweet)
                self.modtweets[tweet[0]] = tweet[1]
                if tweet[1] & utils.TagFavorited:
                    #self.api.create_favorite(tweet[0])
                    self.terminal.write(' {0:<2}'.format('\x1b[1;33m★\x1b[0m'))
                    utils.drawCursorAt(self.terminal, self.cursor, 0, i)
                else:
                    #self.api.destroy_favorite(tweet[0])
                    self.terminal.write('   ')
                    utils.drawCursorAt(self.terminal, self.cursor, 0, i)
        elif keyID == 'f':#mark all as read
            for t in self.tweets:
                if not (t[1] & utils.TagRead):
                    self.modtweets[t[0]] = (t[1] | utils.TagRead)
            for i in xrange(len(self.tweets)):
                tweet = list(self.tweets[i])
                tweet[1] = tweet[1] | utils.TagRead
                self.tweets[i] = tuple(tweet)
            self.cursorX = self.terminal.cursorPos.x
            self.cursorY = self.terminal.cursorPos.y
            self.showPage()
            utils.moveCursorTo(self.terminal, self.cursor, self.cursorX, self.cursorY)
        elif keyID == 'a':#同作者更早
            p = self.terminal.cursorPos.y
            if p >= 3 and p <= len(self.templist)+2:
                idx = self.pagecursor*20+(p-3)
                idindex = 8
                if self.isDM:
                    idindex = 6
                for i in xrange(idx+1,len(self.tweets)):
                    if self.tweets[i][idindex] == self.tweets[idx][idindex]:
                        self.pagecursor = i / 20
                        self.showPage()
                        utils.moveCursorTo(self.terminal, self.cursor, 0, i%20 + 3)
                        break
        elif keyID == 'A':#同作者更晚
            p = self.terminal.cursorPos.y
            if p >= 3 and p <= len(self.templist)+2:
                idx = self.pagecursor*20+(p-3)
                idindex = 8
                if self.isDM:
                    idindex = 6
                for i in xrange(idx-1, -1, -1):
                    if self.tweets[i][idindex] == self.tweets[idx][idindex]:
                        self.pagecursor = i / 20
                        self.showPage()
                        utils.moveCursorTo(self.terminal, self.cursor, 0, i%20 + 3)
                        break
        elif keyID == '\x01':#Ctrl-a, show profilepage
            i = self.terminal.cursorPos.y
            if i >= 3 and i <= len(self.templist)+2:
                self.cursorX = self.terminal.cursorPos.x
                self.cursorY = self.terminal.cursorPos.y
                if self.isDM:
                    info = self.tweets[self.pagecursor*20+(i-3)][6:14]
                else:
                    info = self.tweets[self.pagecursor*20+(i-3)][8:16]
                self.curpage = profilePage(self.terminal, info, self.callback)

#========================================================
class tweetPage:
    '''tweet page'''
    def __init__(self, api, user, tuser, dbcursor, terminal,
            tweets, tweetcursor, modtweets, pcallback):
        self.api = api
        self.user = user
        self.tuser = tuser
        self.dbcursor = dbcursor
        self.terminal = terminal
        self.tweets = tweets
        self.tweetcursor = tweetcursor
        self.modtweets = modtweets
        self.pcallback = pcallback
        self.cursor = consts.CURSOR
        self.cursorX, self.cursorY = 0, 0
        self.curpage = None

        self.show()

    def show(self):
        '''show the tweet'''
        tweet = self.tweets[self.tweetcursor]
        self.modtweets[tweet[0]] = tweet[1] | utils.TagRead
        tweet = list(tweet)
        tweet[1] = tweet[1] | utils.TagRead
        tweet = tuple(tweet)
        self.tweets[self.tweetcursor] = tweet
        t = tweet[3].encode('utf-8')
        t = time.strptime(t, "%a %b %d %H:%M:%S +0000 %Y")
        t = time.strftime("%Y.%m.%d %H:%M:%S", time.localtime(calendar.timegm(t)))
        head = '\x1b[1;33m{0:<6}: {1}({2})\r\n'.format('作者', tweet[10].encode('utf-8'),\
                tweet[9].encode('utf-8'))\
                + '\x1b[1;33m{0:<6}: {1}\r\n'.format('时间', t)\
                + '\x1b[1;33m{0:<6}: {1}\r\n'.format('来源', tweet[4].encode('utf-8'))

        content = '\x1b[1;37m\r\n{0}\r\n'.format(tweet[5].encode('utf-8'))

        if tweet[6]:
            found = False
            for t in self.tweets:
                if tweet[6] == t[0]:
                    content += '\x1b[1;34m\r\n【@%s 说:】\r\n\x1b[1;32m%s\r\n' % (\
                            t[10].encode('utf-8'), t[5].encode('utf-8'))
                    found = True
                    break
            if not found:
                #TODO 可以根据消息文本开始处的用户名自己生成一个链接:
                #http://twitter.com/daizw/status/9633364542
                #TODO 这里有些问题，有些tweet的开头并不是用户名
                content += '\x1b[1;34m\r\n【In Reply To】\r\n\x1b[1;32m http://twitter.com/%s/status/%d\r\n' % (\
                        tweet[5].split()[0][1:].encode('utf-8'),
                        tweet[6])
        
        foot = '\x1b[1;33m\r\n------\r\n ◆ {0:<6}: {1:<70}\x1b[0m'.format('位置',\
                'Tw!term(http://code.google.com/p/twiterm/)')

        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.terminal.write(head + content + foot)

    def callback(self, *args):
        '''called by sub-pages'''
        del self.curpage
        self.curpage = None
        self.show()

    def keystrokeReceived(self, keyID, modifier):
        '''处理键盘事件'''
        if self.curpage:
            self.curpage.keystrokeReceived(keyID, modifier)
            return

        if keyID == self.terminal.UP_ARROW or keyID == '\x1b[OA'\
                or keyID == 'k' or keyID == self.terminal.PGUP:
            if self.tweetcursor > 0:
                self.tweetcursor -= 1
                self.show()
        elif keyID == self.terminal.DOWN_ARROW or keyID == '\x1b[OB'\
                or keyID == 'j' or keyID == self.terminal.PGDN\
                or keyID == ' ' or keyID == self.terminal.RIGHT_ARROW:
            if self.tweetcursor < len(self.tweets)-1:
                self.tweetcursor += 1
                self.show()
        elif keyID == self.terminal.LEFT_ARROW or keyID == '\x1b[OD' or keyID == 'e' or keyID == 'q':
            self.pcallback(self.tweetcursor)
        elif keyID == 'r':
            self.cursorX = self.terminal.cursorPos.x
            self.cursorY = self.terminal.cursorPos.y
            tweet = self.tweets[self.tweetcursor]
            self.curpage = postPage(self.api, self.terminal, self.callback, tweet, type=1)
        elif keyID == 'c':
            self.cursorX = self.terminal.cursorPos.x
            self.cursorY = self.terminal.cursorPos.y
            tweet = self.tweets[self.tweetcursor]
            self.curpage = postPage(self.api, self.terminal, self.callback, tweet, type=2)
        elif keyID == 'm':
            self.cursorX = self.terminal.cursorPos.x
            self.cursorY = self.terminal.cursorPos.y
            tweet = self.tweets[self.tweetcursor]
            self.curpage = postPage(self.api, self.terminal, self.callback, tweet, type=3)
        #TODO r:回复 m:dm作者 t:官方ReTweet f:favorite c:附评论RT

#========================================================
class dmPage:
    '''direct message page'''
    def __init__(self, api, user, tuser, dbcursor, terminal,
            tweets, tweetcursor, modtweets, pcallback):
        self.api = api
        self.user = user
        self.tuser = tuser
        self.dbcursor = dbcursor
        self.terminal = terminal
        self.tweets = tweets
        self.tweetcursor = tweetcursor
        self.modtweets = modtweets
        self.pcallback = pcallback
        self.cursor = consts.CURSOR
        self.cursorX, self.cursorY = 0, 0
        self.curpage = None

        self.show()

    def show(self):
        '''show the tweet'''
        tweet = self.tweets[self.tweetcursor]
        self.modtweets[tweet[0]] = tweet[1] | utils.TagRead
        tweet = list(tweet)
        tweet[1] = tweet[1] | utils.TagRead
        tweet = tuple(tweet)
        self.tweets[self.tweetcursor] = tweet
        t = tweet[4].encode('utf-8')
        t = time.strptime(t, "%a %b %d %H:%M:%S +0000 %Y")
        t = time.strftime("%Y.%m.%d %H:%M:%S", time.localtime(calendar.timegm(t)))
        head = '\x1b[1;33m{0:<9}: {1}({2})\r\n'.format('发信人', \
                tweet[8].encode('utf-8'), tweet[7].encode('utf-8'))\
                + '\x1b[1;33m{0:<9}: {1}({2})\r\n'.format('收信人', \
                tweet[16].encode('utf-8'), tweet[15].encode('utf-8'))\
                + '\x1b[1;33m{0:<8}: {1}\r\n'.format('时  间', t)

        content = '\x1b[1;37m\r\n{0}\r\n'.format(tweet[5].encode('utf-8'))
        
        foot = '\x1b[1;33m\r\n------\r\n ◆ {0:<6}: {1:<70}\x1b[0m'.format('位置',\
                'Tw!term(http://code.google.com/p/twiterm/)')

        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.terminal.write(head + content + foot)

    def callback(self, *args):
        '''called by sub-pages'''
        del self.curpage
        self.curpage = None
        self.show()

    def keystrokeReceived(self, keyID, modifier):
        '''处理键盘事件'''
        if self.curpage:
            self.curpage.keystrokeReceived(keyID, modifier)
            return

        if keyID == self.terminal.UP_ARROW or keyID == '\x1b[OA'\
                or keyID == 'k' or keyID == self.terminal.PGUP:
            if self.tweetcursor > 0:
                self.tweetcursor -= 1
                self.show()
        elif keyID == self.terminal.DOWN_ARROW or keyID == '\x1b[OB'\
                or keyID == 'j' or keyID == self.terminal.PGDN\
                or keyID == ' ' or keyID == self.terminal.RIGHT_ARROW:
            if self.tweetcursor < len(self.tweets)-1:
                self.tweetcursor += 1
                self.show()
        elif keyID == self.terminal.LEFT_ARROW or keyID == '\x1b[OD' or keyID == 'e' or keyID == 'q':
            self.pcallback(self.tweetcursor)
        elif keyID == 'r':
            self.cursorX = self.terminal.cursorPos.x
            self.cursorY = self.terminal.cursorPos.y
            tweet = self.tweets[self.tweetcursor]
            self.curpage = postPage(self.api, self.terminal, self.callback, tweet, type=3)

#========================================================
class postPage:
    '''tweet page'''
    def __init__(self, api, terminal, pcallback, tweet=None, type=0):
        '''@ivar param type: 
        0: normal post;
        1: reply;
        2: RT;
        3: direct message
        '''
        self.api = api
        self.terminal = terminal
        self.pcallback = pcallback
        self.tweet = tweet
        self.type = type

        self.cursorX, self.cursorY = 0, 0

        self.buffer = []
        self.limit = 140

        #width of wide char
        self.width = 3
        self.count = 0

        ts = ''
        if self.type == 1:
            ts = '@%s ' % tweet[10].encode('utf-8')
        elif self.type == 2:
            ts = 'RT @%s: %s' % (tweet[10].encode('utf-8'), tweet[5].encode('utf-8'))
        elif self.type == 3:
            if len(tweet) == 16:#tweet
                ts = 'dm %s ' % tweet[10].encode('utf-8')
            elif len(tweet) == 22:#direct message
                ts = 'dm %s ' % tweet[8].encode('utf-8')
            else:
                print len(tweet), repr(tweet)
                raise Exception('Funny tweet tuple')
        for c in ts:
            self.buffer.append(c)
        self.show()

    def show(self):
        '''show the tweet'''

        head = '\x1b[1;33;44m{0:>3}/{1} {2:>72}\x1b[0m\r\n'.format(\
                self.limit - len(''.join(self.buffer).decode('utf-8')),
                self.limit,
                'Post: press Enter twice | Cancel: press Esc twice')

        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.terminal.write(head)
        self.terminal.write(''.join(self.buffer))

    def callback(self, *args):
        '''called by sub-pages'''

    def keystrokeReceived(self, keyID, modifier):
        '''处理键盘事件'''

        if keyID == '\r':
            if self.buffer and self.buffer[-1] == '\n':
                self.terminal.write(' posting...')
                st = ''.join(self.buffer).strip()
                if st:
                    if self.type == 1:
                        self.api.update_status(status = st,
                                in_reply_to_status_id = str(self.tweet[0]))
                    else:
                        self.api.update_status(st)
                self.pcallback()
            else:
                self.buffer.append('\n')
                self.terminal.write('\r\n')
                #self.cursorX = self.terminal.cursorPos.x
                #self.cursorY = self.terminal.cursorPos.y
                #self.show()
                #utils.setCursorPosition(self.terminal, self.cursorX, self.cursorY)
        elif str(keyID) in string.printable:
            self.buffer.append(keyID)
            self.show()
        elif keyID == self.terminal.BACKSPACE:
            if self.buffer:
                if str(self.buffer[-1]) in string.printable:
                    del self.buffer[-1]
                    self.terminal.cursorBackward()
                    self.terminal.write(' ')
                    self.terminal.cursorBackward()
                else:
                    self.buffer = self.buffer[:-3]
                    self.terminal.cursorBackward()
                    self.terminal.cursorBackward()
                    self.terminal.write('  ')
                    self.terminal.cursorBackward()
                    self.terminal.cursorBackward()
            self.show()
        elif keyID == '\x1b' and modifier == self.terminal.ALT:
            self.pcallback()
        elif keyID in insults.FUNCTION_KEYS:
            pass
        else:
            self.buffer.append(keyID)
            self.count += 1
            if self.count == 3:
                self.count = 0
                self.show()


#========================================================
class profilePage:
    '''profile page'''
    def __init__(self, terminal, info, pcallback):
        self.terminal = terminal
        self.info = list(info)
        self.pcallback = pcallback
        self.curpage = None

        for i in xrange(len(self.info)):
            if not self.info[i]:
                self.info[i] = ''

        self.show()

    def show(self):
        '''show the profile'''
        content = '\x1b[1;33m{0:<8}: {1}(@{2})\r\n'.format('Name', self.info[1].encode('utf-8'),\
                self.info[2].encode('utf-8'))\
                + '\x1b[1;33m{0:<8}: {1}\r\n'.format('Location', self.info[3].encode('utf-8'))\
                + '\x1b[1;33m{0:<8}: {1}\r\n'.format('Web', self.info[6].encode('utf-8'))\
                + '\x1b[1;33m{0:<8}: {1}\r\n'.format('Avatar', self.info[5].encode('utf-8'))\
                + '\x1b[1;33m{0:<8}: {1}\r\n'.format('Bio', self.info[4].encode('utf-8'))

        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.terminal.write(content)

    def callback(self, *args):
        '''called by sub-pages'''
        del self.curpage
        self.curpage = None
        self.show()

    def keystrokeReceived(self, keyID, modifier):
        '''处理键盘事件'''
        if self.curpage:
            self.curpage.keystrokeReceived(keyID, modifier)
            return

        self.pcallback()

