import os
import logging
import hypchat

from toolkit_base import ToolkitBase
from configuration import get_config, handle_missing_config

hipchat_token = os.environ.get('HIPCHAT_TOKEN')

def get_hipchat_token():
    global hipchat_token
    if hipchat_token != None:
        return hipchat_token
    hipchat_token = get_config("hipchat.token")
    if hipchat_token is None:
        handle_missing_config("Please set your Hipchat private API token (you can grab it from here https://evme.hipchat.com/account/api):", 'hipchat.token')
    else:
        return hipchat_token

instance = None

def get_instance():
    global instance
    if instance is None:
        instance = hypchat.HypChat(get_hipchat_token())
    return instance

def get_hipchat_user():
    h = get_instance()
    import urllib2, json

    try:
        j = urllib2.urlopen('{0}/v2/oauth/token/{1}?auth_token={1}'.format(h.endpoint, get_hipchat_token())).read()
        j = json.loads(j)
        return j['owner']['mention_name']
    except Exception,e:
        logging.error("Couldn't fetch Hipchat username: %r" % e)
        return None


class SendMessage(object):
    METHOD = "send-message"
    DOC = "Sends a message to a user/room"

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("recipient", help="user/room to send the message to")
        parser.add_argument("message", help="message to send")

    def handle(self, namespace):
        self(namespace.recipient, namespace.message)

    def __call__(self, recipient, message):
        H = get_instance()
        u = None
        try:
            u = H.get_user('@%s' % recipient).message
        except Exception:
            try:
                u = H.get_room(recipient).notification
            except Exception, e:
                print e
        try:
            if u is not None:
                u(message)
                return True
        except Exception, e:
            print str(e)
        return False


class TestConnection(object):
    METHOD = "test-connection"
    DOC = "Test the hipchat server connection"

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        print self()

    def __call__(self):
        H = get_instance()
        try:
            return H.rooms()['items'] > 0
        except Exception, e:
            print str(e)
            return False
