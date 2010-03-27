#!/usr/bin/python
# coding: utf-8

import hashlib
import sqlite3 as sqlite

from zope.interface import implements

from twisted.internet import defer
from twisted.python import failure, log
from twisted.cred import error, credentials
from twisted.cred.checkers import ICredentialsChecker

def hash(username, password, u):
    '''A function used to transform the plaintext password
    received over the network to a format suitable for comparison
    against the version stored on disk.  The arguments to the callable
    are the username, the network-supplied password, and the in-file
    version of the password.  If the return value compares equal to the
    version stored on disk, the credentials are accepted.

    @return md5(username+md5(password))
    '''
    m = hashlib.md5()
    m.update(password)
    mm = hashlib.md5()
    mm.update(username)
    mm.update(m.hexdigest())
    print '===', username, password, u
    print '===', mm.hexdigest()
    return mm.hexdigest()

class PasswordDBChecker:
    """A database-based, text-based username/password checker.

    Records in the datafile for this class are delimited by a particular
    string.  The username appears in a fixed field of the columns delimited
    by this string, as does the password.  Both fields are specifiable.  If
    the passwords are not stored plaintext, a hash function must be supplied
    to convert plaintext passwords to the form stored on disk and this
    CredentialsChecker will only be able to check IUsernamePassword
    credentials.  If the passwords are stored plaintext,
    IUsernameHashedPassword credentials will be checkable as well.
    """

    implements(ICredentialsChecker)

    def __init__(self, dbname, hash=None, caseSensitive=False):
        """
        @type dbname: C{str}
        @param dbname: The name of the database file from which to read username and
        password information.

        @type caseSensitive: C{bool}
        @param caseSensitive: If true, consider the case of the username when
        performing a lookup.  Ignore it otherwise.

        @type hash: Three-argument callable or C{None}
        @param hash: A function used to transform the plaintext password
        received over the network to a format suitable for comparison
        against the version stored on disk.  The arguments to the callable
        are the username, the network-supplied password, and the in-file
        version of the password.  If the return value compares equal to the
        version stored on disk, the credentials are accepted.
        """
        self.dbname = dbname
        self.caseSensitive = caseSensitive
        self.hash = hash

        if self.hash is None:
            # The passwords are stored plaintext.  We can support both
            # plaintext and hashed passwords received over the network.
            self.credentialInterfaces = (
                credentials.IUsernamePassword,
                credentials.IUsernameHashedPassword
            )
        else:
            # The passwords are hashed on disk.  We can support only
            # plaintext passwords received over the network.
            self.credentialInterfaces = (
                credentials.IUsernamePassword,
            )

    def __getstate__(self):
        return dict(vars(self))

    def _cbPasswordMatch(self, matched, username):
        if matched:
            return username
        else:
            return failure.Failure(error.UnauthorizedLogin())

    def getUser(self, username):
        if not self.caseSensitive:
            username = username.lower()

        try:
            conn = sqlite.connect(self.dbname)
            conn.isolation_level = None
            cursor = conn.cursor()
            cursor.execute('select name,pass from sysusers where name=?', (username,))
            up = cursor.fetchone()
            print up
            if not up:
                raise KeyError(username)
        except:
            print "!!!!!!!!!! what's wrong?!"
            log.err()
            raise error.UnauthorizedLogin()
        else:
            return up

    def requestAvatarId(self, c):
        # 新用户
        if c.username.lower() == 'new':
            return defer.succeed(c.username)
        try:
            u, p = self.getUser(c.username)
            print u, p
        except KeyError:
            return defer.fail(error.UnauthorizedLogin())
        else:
            print '++++++++before'
            up = credentials.IUsernamePassword(c, None)
            print '++++++++after'
            print up
            if self.hash:
                if up is not None:
                    h = self.hash(up.username, up.password, p)
                    if h == p:
                        return defer.succeed(u)
                return defer.fail(error.UnauthorizedLogin())
            else:
                return defer.maybeDeferred(c.checkPassword, p
                    ).addCallback(self._cbPasswordMatch, u)

