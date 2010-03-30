#!/usr/bin/python
# encoding: utf-8
#
# Copyright (c) 2010 shinysky
# See LICENSE for details.
#

import string
import time
import sqlite3 as sqlite

from twisted.python import log
from twisted.conch.insults import insults
from twisted.conch.telnet import TelnetTransport, TelnetBootstrapProtocol
from twisted.internet import threads
from twisted.internet import protocol, defer, task, reactor
from twisted.application import internet, service
from twisted.cred import checkers, portal

import pwdchecker
import pages
import utils
import consts
from manhole_ssh import ConchFactory, TerminalRealm

#reactor.suggestThreadPoolSize(20) # 线程池大小

# to remember the
# connection number of one user
userstate = {}
# every online twitter user has a updater
# to update timelines
updaters = {}

class TtermProtocol(insults.TerminalProtocol):
    """Protocol for tweeting in terminal.
    """

    def __init__(self):
        self.width = 80
        self.height = 24
        self.buffer = []
        self.count = 0
        self.cursor = consts.CURSOR
        self.apis = {}
        self.curpage = None #current page

    #assuming: One account, One connection, One binding twitter user
    def connectionMade(self):
        self.user = self.terminal.transport.avatarId
        print '==== username:', self.user

        self.terminal.eraseDisplay()
        self.terminal.resetModes([insults.modes.IRM])
        self.buffer = []
        self.terminalSize(self.width, self.height)

        #TODO 第一个连接开启updater, 最后一个连接停止updater
        # read DB, increase connection num
        # bring up a updater for every binding if this is the first connection
        connnum = self.updateConnectionNum(True)

        self.dbconn = sqlite.connect("data.db")
        self.dbconn.isolation_level = None
        self.dbcursor = self.dbconn.cursor()

        # 注册新用户
        if self.user == 'new':
            self.curpage = pages.registerPage(self.dbcursor, self.terminal)
            return

        # get every binding twitter account
        self.dbcursor.execute('select * from bindings \
                inner join twitterusers \
                on bindings.id=twitterusers.id \
                where bindings.owner=?', (self.user,))
        self.bindings = self.dbcursor.fetchall()

        # 如果未绑定帐号, 执行绑定
        if not self.bindings:
            self.curpage = pages.bindingPage(self.user, self.dbcursor, self.terminal)
            return

        for b in self.bindings:
            api = utils.getTwitterApi(b[2], b[3])
            self.apis[b[0]] = api
            # bring up a loopingcall for everyone.
            global updaters
            if b[0] not in updaters:
                #TODO bring up a loopingcall
                # and store it in the updaters
                threads.deferToThread(self.runUpdater, b[0], api, 60)

        tusers = [(b[0],b[7]) for b in self.bindings]

        self.curpage = pages.mainListPage(self.apis, self.user, tusers, self.dbcursor, self.terminal)

        #self.terminal.eraseDisplay()
        #self.terminal.cursorHome()
        #self.terminal.write(pages.getStatusListPageStr(self.user, 'Home', self.getHomeTimeline()))
        #utils.setCursorPosition(self.terminal, 0, 3)
        #self.terminal.write(self.cursor)
        #self.terminal.cursorBackward()

    def connectionLost(self, reason):
        '''called when connection lost'''
        # stop updater
        self.stopUpdaters()
        connnum = self.updateConnectionNum(False)
        if connnum <= 0:
            self.stopUpdaters()
        self.dbconn.close()

    def updateConnectionNum(self, bIncrease = True):
        '''increase or decrease connection number
        @param bIncrease is True if to increase, False otherwise
        '''
        global userstate
        if self.user in userstate:
            if bIncrease: userstate[self.user] += 1
            else: userstate[self.user] -= 1
        else:
            if not bIncrease:
                raise Exception, 'Internal Error, userstate fault'
            userstate[self.user] = 1
        return userstate[self.user]

    def runUpdater(self, tuid, api, interval=12):
        '''called when connection made
        @param tuid: twitter user id
        '''
        ud = task.LoopingCall(self._iterate, tuid, api, interval)
        ud.start(interval)
        global updaters
        updaters[tuid] = ud
    
    def stopUpdaters(self):
        '''called when the last connection lost'''
        global updaters
        for n,k,s in self.bindings:
            if n in updaters:
                updaters[n].stop()
                del updaters[n]

    def _iterate(self, tuid, api, interval=12):
        '''@param tuid: twitter user id'''
        threads.deferToThread(utils.updateHomeTimeline, tuid, api)
        threads.deferToThread(utils.updateMentions, tuid, api)
        threads.deferToThread(utils.updateDirectMessages, tuid, api)
        threads.deferToThread(utils.updateSentDirectMessages, tuid, api)
        #utils.updateHomeTimeline(tuid, api)
        ##TODO 阻塞问题; dm不需要更新这么频繁吧...
        #utils.updateMentions(tuid, api)
        #utils.updateDirectMessages(tuid, api)
        #utils.updateSentDirectMessages(tuid, api)

    # ITerminalListener
    def terminalSize(self, width, height):
        self.width = width
        self.height = height
    
    def setCursorPosition(self, column, line):
        '''twisted.conch原来的实现似乎有bug, 没有设定本地的值'''
        self.terminal.cursorPos.x = column
        self.terminal.cursorPos.y = line
        self.terminal.write('\x1b[%d;%dH' % (line + 1, column + 1))

    def unhandledControlSequence(self, seq):
        #pcmanx will send this kind of symbols
        if seq.startswith('\x1b[O') or seq == '\x1b[8~' or seq == '\x1b[7~':
            self.keystrokeReceived(seq, None)
        else:
            log.msg("Client sent something weird: %r" % (seq,))

    def keystrokeReceived(self, keyID, modifier):
        print '=== keystrokeReceived()', repr(keyID), repr(modifier)
        #Ctrl+C
        if keyID == '\x03':
            self.terminal.loseConnection()
        elif self.curpage:
            self.curpage.keystrokeReceived(keyID, modifier)

#-----------------------------------------------------------

def makeService(args):
    checker = pwdchecker.PasswordDBChecker('data.db', pwdchecker.hash, False)

    def chainProtocolFactory():
        return insults.ServerProtocol(
            args['protocol'],
            *args.get('protocolArgs', ()),
            **args.get('protocolKwArgs', {}))

    rlm = TerminalRealm()
    rlm.chainedProtocolFactory = chainProtocolFactory
    ptl = portal.Portal(rlm, [checker])
    f = ConchFactory(ptl)
    csvc = internet.TCPServer(args['ssh'], f)

    m = service.MultiService()
    csvc.setServiceParent(m)
    return m

application = service.Application("tterm")
makeService({'protocol': TtermProtocol,
             'ssh': 6022}).setServiceParent(application)

