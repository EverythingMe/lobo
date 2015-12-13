class NopObj(object):

    def __getattr__(self,name):
        return ""

def nop_func(*args,**kw):
    return NopObj()

class NopDriver(object):

    def __getattr__(self,name):
        return nop_func
