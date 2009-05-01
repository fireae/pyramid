import threading

import zope.component

from zope.component import getGlobalSiteManager
from zope.component import getSiteManager as original_getSiteManager
from zope.component.interfaces import ComponentLookupError
from zope.component.interfaces import IComponentLookup
from zope.component.registry import Components

from zope.deprecation import deprecated

from repoze.bfg.zcml import zcml_configure

from repoze.bfg.settings import Settings  # alias for deprecation below

deprecated('Settings',
    "('from repoze.bfg.registry import Settings' is now "
    "deprecated; instead use 'from repoze.bfg.settings import Settings')",
    )

from repoze.bfg.settings import get_options # alias for deprecation below

deprecated('get_options',
    "('from repoze.bfg.registry import get_options' is now "
    "deprecated; instead use 'from repoze.bfg.settings import get_options')",
    )

class Registry(Components):

    # for optimization purposes, if no listeners are listening, don't try
    # to notify them
    has_listeners = False

    def registerSubscriptionAdapter(self, *arg, **kw):
        result = Components.registerSubscriptionAdapter(self, *arg, **kw)
        self.has_listeners = True
        return result
        
    def registerHandler(self, *arg, **kw):
        result = Components.registerHandler(self, *arg, **kw)
        self.has_listeners = True
        return result

    def notify(self, *events):
        if self.has_listeners:
            # iterating over subscribers assures they get executed
            for ignored in self.subscribers(events, None):
                """ """

class ThreadLocalRegistryManager(threading.local):
    def __init__(self):
        self.stack = []
        
    def push(self, registry):
        self.stack.append(registry)

    set = push # backwards compatibility

    def pop(self):
        if self.stack:
            return self.stack.pop()

    def get(self):
        try:
            return self.stack[-1]
        except IndexError:
            return getGlobalSiteManager()

    def clear(self):
        self.stack[:] = []

registry_manager = ThreadLocalRegistryManager()

def setRegistryManager(manager): # for unit tests
    global registry_manager
    old_registry_manager = registry_manager
    registry_manager = manager
    return old_registry_manager

def populateRegistry(registry, filename, package, lock=threading.Lock()):

    """ We push our ZCML-defined configuration into an app-local
    component registry in order to allow more than one bfg app to live
    in the same process space without one unnecessarily stomping on
    the other's component registrations (although I suspect directives
    that have side effects are going to fail).  The only way to do
    that currently is to override zope.component.getGlobalSiteManager
    for the duration of the ZCML includes.  We acquire a lock in case
    another make_app runs in a different thread simultaneously, in a
    vain attempt to prevent mixing of registrations.  There's not much
    we can do about non-makeRegistry code that tries to use the global
    site manager API directly in a different thread while we hold the
    lock.  Those registrations will end up in our application's
    registry."""
    
    lock.acquire()
    registry_manager.push(registry)
    try:
        original_getSiteManager.sethook(getSiteManager)
        zope.component.getGlobalSiteManager = registry_manager.get
        zcml_configure(filename, package=package)
    finally:
        zope.component.getGlobalSiteManager = getGlobalSiteManager
        lock.release()
        registry_manager.pop()

def getSiteManager(context=None):
    if context is None:
        return registry_manager.get()
    else:
        try:
            return IComponentLookup(context)
        except TypeError, error:
            raise ComponentLookupError(*error.args)

from zope.testing.cleanup import addCleanUp
addCleanUp(original_getSiteManager.reset) # AttributeError: zope.hookable not installed
addCleanUp(registry_manager.clear)
