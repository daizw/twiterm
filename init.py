#!/usr/bin/python
# encoding: utf-8
#
# Copyright (c) 2010 shinysky
# See LICENSE for details.

import sqlite3 as sqlite

def runOnce(dbname):
    '''init database'''
    conn = sqlite.connect(dbname)
    # 系统用户名,密码
    conn.execute("create table if not exists sysusers(name text primary key, pass text, other text)")
    # 已绑定twitter帐号的信息
    conn.execute('''create table if not exists bindings(
        id integer primary key,
        owner text,
        key text,
        secret text,
        other text,
        foreign key(owner) references sysusers(name))''')
    # 所有已知twitter用户的信息
    conn.execute('''create table if not exists twitterusers(
        id integer primary key,
        name text,
        screenname text,
        location text,
        description text,
        profileimage text,
        url text,
        other text)''')
    conn.commit()
    conn.close()

if __name__ == '__main__':
    runOnce("data.db")

