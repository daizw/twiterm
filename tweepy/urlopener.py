
#set global timeout in seconds
import socket
import urllib2
import cookielib

class UrlOpener:
    '''a customed url opener'''
    def __init__(self):
        timeout = 10
        socket.setdefaulttimeout(timeout)
        self.buildOpener()

    def buildOpener(self):
        # set up authentication info
        self.authinfo = urllib2.HTTPBasicAuthHandler()
        self.authinfo.add_password(realm='localhost',
                              uri='http://localhost:8000',
                              user='',
                              passwd='')

        self.http_proxy_handler = urllib2.ProxyHandler({"http" : "http://localhost:8000"})
        self.https_proxy_handler = urllib2.ProxyHandler({"https" : "https://localhost:8000"})

        # build a new opener that adds authentication and caching FTP handlers
        self.cookies = cookielib.CookieJar()
        self.opener = urllib2.build_opener(self.http_proxy_handler,
                self.https_proxy_handler,
                self.authinfo,
                urllib2.HTTPCookieProcessor(self.cookies))

    def doGet(self, url, headers):
        '''HTTP GET Method'''
        request = urllib2.Request(url, headers = headers)
        return self.opener.open(request)

    def doPost(self, targetUrl, paramDict, headers, refererUrl=''):
        '''HTTP POST Method'''
        if len(refererUrl) > 0:
            headers['Referer'] = refererUrl

        poster = urllib2.Request(targetUrl, '', headers)

        return self.opener.open(poster)
