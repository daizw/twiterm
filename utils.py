#!/usr/bin/python
# encoding: utf-8
#
# Copyright (c) 2010 shinysky
# See LICENSE for details.
#

import sys, traceback
import sqlite3 as sqlite
import re

import tweepy
import simplejson as json

import consts

TagHome = 0x1
TagMentions = 0x2
TagRetweet = 0x4
TagFavorited = 0x8
TagRead = 0x10

def getTermLength(ss):
    '''return the length of a string in the terminal.
    ss: unicode string
    ex. getLength(u'我') = 2
    '''
    s = ss.encode('utf-8')
    return len(ss) + (len(s) - len(ss))/2
    #count = 0
    #for c in s:
    #    if ord(c) > 127:
    #        count += 1
    #return len(s) - count/3

def split(ss, length):
    '''split a long string to short strings
    ss: unicode string
    '''
    res = []
    while ss:
        if getTermLength(ss) <= length:
            res.append(ss)
            break
        for i in xrange(1, len(ss)):
            if getTermLength(ss[:i]) > length:
                res.append(ss[:i-1])
                ss = ss[i-1:]
                break
    return res

def getTableNames(tuser):
    return 'x%d'%tuser, 'd%d'%tuser

def cursorUp(terminal, cursor):
    terminal.write(' ')
    terminal.cursorBackward()
    terminal.cursorUp()
    terminal.write(cursor)
    terminal.cursorBackward()

def cursorDown(terminal, cursor):
    terminal.write(' ')
    terminal.cursorBackward()
    terminal.cursorDown()
    terminal.write(cursor)
    terminal.cursorBackward()

def setCursorPosition(terminal, column, line):
    '''twisted.conch原来的实现似乎有bug, 没有设定本地的值'''
    terminal.cursorPos.x = column
    terminal.cursorPos.y = line
    terminal.write('\x1b[%d;%dH' % (line + 1, column + 1))

def drawCursorAt(terminal, cursor, x, y):
    '''move cursor to (x,y), and draw a cursor there'''
    terminal.write(' ')
    setCursorPosition(terminal, x, y)
    terminal.write(cursor)
    terminal.cursorBackward()

def parseSource(s):
    '''convert source string
    '<a href="http://darter/" rel="nofollow">Darter</a>'
    to 'Darter(http://darter/)'
    '''
    if s.lower() == 'web':
        return s
    else:
        p = re.compile('<[^>]*"(http[^\s]*)"[^>]*>([^<]*)</a>')
        m = p.match(s)
        if m:
            return '%s(%s)' % (m.groups()[1], m.groups()[0])
    return s

def getTwitterApi(key, secret):
    #OAuth
    auth = tweepy.OAuthHandler(consts.CONSUMER_KEY, consts.CONSUMER_SECRET)
    auth.set_access_token(key, secret)
    
    print 'access token key:', auth.access_token.key
    print 'access token secret:', auth.access_token.secret
    
    # Construct the API instance
    return tweepy.API(auth)

def saveTwitterUser(dbcursor, user):
    '''insert a twitter user into DB
    @param user: a dict containing user info
    '''
    try:
        dbcursor.execute("insert into twitterusers values(?,?,?,?,?,?,?,?)",
                (user['id'],
                    user['name'],
                    user['screen_name'],
                    user['location'],
                    user['description'],
                    user['profile_image_url'],
                    user['url'],
                    None))
    except:
        # 重复的, 更新之
        try:
            #UPDATE Person SET Address = 'Zhongshan 23', City = 'Nanjing'
            #WHERE LastName = 'Wilson'
            #DELETE FROM Person WHERE LastName = 'Wilson' 
            dbcursor.execute("update twitterusers set id = ?,\
                    name = ?,\
                    screenname = ?,\
                    location = ?,\
                    description = ?,\
                    profileimage = ?,\
                    url = ?,\
                    other = ? \
                    where id = ?",
                    (user['id'],
                        user['name'],
                        user['screen_name'],
                        user['location'],
                        user['description'],
                        user['profile_image_url'],
                        user['url'],
                        None,
                        user['id']))

        except:
            traceback.print_exc(file=sys.stdout)

def updateHomeTimeline(uid, api):
    '''update home_timeline, and write it into DB'''
    # read DB, find the since_id, make it 0 if DB is empty
    # fetch home_timeline with API
    # process the result
    # write it into DB
    #TODO select max(id) from...
    conn = sqlite.connect('data.db')
    dbcursor = conn.cursor()
    dbcursor.execute("select id, tag from %s order by id desc" % ('x%d'%uid))
    resp = ''
    while True:
        id = dbcursor.fetchone()
        #print 'since_id candidate:', id
        if id:
            if (id[1] & TagHome):
                resp = api.home_timeline(since_id = id[0], count=200)
                break
            else:
                continue
        else:
            #取最近的200个
            resp = api.home_timeline(count = 200)
            break
    timeline = json.loads(resp)
    print '====================================='
    print timeline
    for s in timeline:
        try:
            saveTwitterUser(dbcursor, s['user'])
            tag = TagHome
            if(s['favorited']):
                tag = tag | TagFavorited
            # 如果tweet原来存在于表中, 取tag按位或, 并且应该使用update, 而不是insert
            print '===! inserting', s['id']
            dbcursor.execute('select tag from %s where id = ?' % ('x%d'%uid),
                    (s['id'],))
            oldtag = dbcursor.fetchone()
            if oldtag:
                dbcursor.execute('update %s set tag = ?' % ('x%d'%uid),
                        (oldtag[0] | tag,))
            else:
                dbcursor.execute('insert into %s values(?,?,?,?,?,?,?,?)' % ('x%d'%uid),
                        (s['id'],
                            tag,
                            s['user']['id'],
                            s['created_at'],
                            parseSource(s['source']),
                            s['text'],
                            s['in_reply_to_status_id'],
                            None))
        except:
            traceback.print_exc(file=sys.stdout)
    conn.commit()
    conn.close()

def updateMentions(uid, api):
    '''update mentions, and write them into DB'''
    conn = sqlite.connect('data.db')
    dbcursor = conn.cursor()
    dbcursor.execute("select id, tag from %s order by id desc" % ('x%d'%uid))
    resp = ''
    while True:
        id = dbcursor.fetchone()
        #print 'since_id candidate:', id
        if id:
            if (id[1] & TagMentions):
                resp = api.mentions(since_id = id[0], count=200)
                break
            else:
                continue
        else:
            #取最近的200个
            resp = api.mentions(count = 200)
            break
    timeline = json.loads(resp)
    print '\x1b[31m!!!=== length of mentions: %d\x1b[0m' % len(timeline) 
    for s in timeline:
        try:
            saveTwitterUser(dbcursor, s['user'])
            tag = TagMentions
            if(s['favorited']):
                tag = tag | TagFavorited
            # 如果tweet原来存在于表中, 取tag按位或, 并且应该使用update, 而不是insert
            dbcursor.execute('select tag from %s where id = ?' % ('x%d'%uid),
                    (s['id'],))
            oldtag = dbcursor.fetchone()
            if oldtag:
                dbcursor.execute('update %s set tag = ?' % ('x%d'%uid),
                        (oldtag[0] | tag,))
            else:
                dbcursor.execute('insert into %s values(?,?,?,?,?,?,?,?)' % ('x%d'%uid),
                        (s['id'],
                        tag,
                        s['user']['id'],
                        s['created_at'],
                        parseSource(s['source']),
                        s['text'],
                        s['in_reply_to_status_id'],
                        None))
        except:
            traceback.print_exc(file=sys.stdout)
    conn.commit()
    conn.close()

def updateDirectMessages(uid, api):
    '''update direct_messages, and write them into DB'''
    conn = sqlite.connect('data.db')
    dbcursor = conn.cursor()
    dbcursor.execute("select id from %s where toid=? order by id desc" % ('d%d'%uid),
            (uid,))
    id = dbcursor.fetchone()
    #print 'since_id candidate:', id
    if id:
        resp = api.direct_messages(since_id = id[0], count=200)
    else:
        #取最近的200个
        resp = api.direct_messages(count = 200)
    timeline = json.loads(resp)
    for s in timeline:
        try:
            saveTwitterUser(dbcursor, s['sender'])
            saveTwitterUser(dbcursor, s['recipient'])
            dbcursor.execute('insert into %s values(?,?,?,?,?,?)' % ('d%d'%uid),
                    (s['id'],
                    0,# tag: read
                    s['sender_id'],
                    s['recipient_id'],
                    s['created_at'],
                    s['text']))
        except:
            traceback.print_exc(file=sys.stdout)
    conn.commit()
    conn.close()

def updateSentDirectMessages(uid, api):
    '''update sent_direct_messages, and write them into DB'''
    conn = sqlite.connect('data.db')
    dbcursor = conn.cursor()
    dbcursor.execute("select id from %s where fromid=? order by id desc" % ('d%d'%uid),
            (uid,))
    id = dbcursor.fetchone()
    #print 'since_id candidate:', id
    if id:
        resp = api.sent_direct_messages(since_id = id[0], count=200)
    else:
        #取最近的200个
        resp = api.sent_direct_messages(count = 200)
    timeline = json.loads(resp)
    for s in timeline:
        try:
            saveTwitterUser(dbcursor, s['sender'])
            saveTwitterUser(dbcursor, s['recipient'])
            dbcursor.execute('insert into %s values(?,?,?,?,?,?)' % ('d%d'%uid),
                    (s['id'],
                    0,# tag: read
                    s['sender_id'],
                    s['recipient_id'],
                    s['created_at'],
                    s['text']))
        except:
            traceback.print_exc(file=sys.stdout)
    conn.commit()
    conn.close()
