# -*- mode: python; python-indent: 4 -*-
"""
*********************************************************************
* (C) 2016 Tail-f Systems                                           *
* NETCONF/YANG PIONEER                                              *
*                                                                   *
* Your Swiss army knife when it somes to basic NETCONF,             *
* YANG module collection, NSO NETCONF NED building, installation    *
* and testing.                                                      *
*********************************************************************
"""

    ######################################################################
    ## IMPORTS & GLOBALS

from __future__ import print_function
import os
import sys
import select
import socket
import threading
import traceback

assert sys.version_info >= (2,7)
# Not tested with anything lower

import _ncs
import _ncs.dp as dp
import _ncs.maapi as maapi
import pioneer.namespaces.pioneer_ns as ns

XT = _ncs.XmlTag
V = _ncs.Value
TV = _ncs.TagValue
from ncs_pyvm import NcsPyVM
_schemas_loaded = False

# operation modules
import pioneer.op.config_op
import pioneer.op.log_op
import pioneer.op.netconf_op
import pioneer.op.yang_op
from pioneer.op.ex import ActionError

def param_default(params, tag, default):
    matching_param_list = [p.v for p in params if p.tag == tag]
    if len(matching_param_list) == 0:
        return default
    return str(matching_param_list[0])

class ActionHandler(threading.Thread):
    handlers = {
        ns.ns.pioneer_delete_state: pioneer.op.config_op.DeleteStateOp,
        ns.ns.pioneer_explore_transitions: pioneer.op.config_op.ExploreTransitionsOp,
        ns.ns.pioneer_import_into_file: pioneer.op.config_op.ImportIntoFileOp,
        ns.ns.pioneer_list_states: pioneer.op.config_op.ListStatesOp,
        ns.ns.pioneer_record_state: pioneer.op.config_op.RecordStateOp,
        ns.ns.pioneer_sync_from_into_file: pioneer.op.config_op.SyncFromIntoFileOp,
        ns.ns.pioneer_transition_to_state: pioneer.op.config_op.TransitionToStateOp,
        ns.ns.pioneer_hello: pioneer.op.netconf_op.HelloOp,
        ns.ns.pioneer_get: pioneer.op.netconf_op.GetOp,
        ns.ns.pioneer_get_config: pioneer.op.netconf_op.GetConfigOp,
        ns.ns.pioneer_build_netconf_ned: pioneer.op.yang_op.BuildNetconfNedOp,
        ns.ns.pioneer_disable: pioneer.op.yang_op.DisableOp,
        ns.ns.pioneer_download: pioneer.op.yang_op.DownloadOp,
        ns.ns.pioneer_enable: pioneer.op.yang_op.EnableOp,
        ns.ns.pioneer_fetch_list: pioneer.op.yang_op.FetchListOp,
        ns.ns.pioneer_show_list: pioneer.op.yang_op.ShowListOp,
        ns.ns.pioneer_check_dependencies: pioneer.op.yang_op.CheckDependenciesOp,
        ns.ns.pioneer_delete: pioneer.op.yang_op.DeleteOp,
        ns.ns.pioneer_build_netconf_ned: pioneer.op.yang_op.BuildNetconfNedOp,
        ns.ns.pioneer_install_netconf_ned: pioneer.op.yang_op.InstallNetconfNedOp,
        ns.ns.pioneer_uninstall_netconf_ned: pioneer.op.yang_op.UninstallNetconfNedOp,
        ns.ns.pioneer_sftp: pioneer.op.yang_op.SftpOp,
        ns.ns.pioneer_print_netconf_trace: pioneer.op.log_op.PrintNetconfTraceOp
    }

    ######################################################################
    ##  CB_ACTION  #######################################################
    ######################################################################

    def cb_action(self, uinfo, op_name, kp, params):
        self.debug("========== pioneer cb_action() ==========")

        dev_name = str(kp[-3][0])
        self.debug("thandle={0} usid={1}".format(uinfo.actx_thandle, uinfo.usid))

        try:
            if op_name.tag not in self.handlers:
                raise ActionError({'error': "Operation not implemented: {0}".format(op_name)})

            handler_cls = self.handlers[op_name.tag]
            handler = handler_cls(self.msocket, uinfo, dev_name, params, self.debug)
            result = handler.perform()
            return self.action_response(uinfo, result)

        ##----------------------------------------------------------------
        except ActionError as ae:
            self.debug("ActionError exception")
            return self.action_response(uinfo, ae.get_info())
        except:
            self.debug("Other exception: " + repr(traceback.format_exception(*sys.exc_info())))
            msg = "Operation failed"
            dp.action_reply_values(uinfo, [TV(XT(ns.ns.hash, ns.ns.pioneer_error), V(msg))])
            return _ncs.CONFD_OK

    def action_response(self, uinfo, result):
        reply = []

        if 'message' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_message), V(result['message']))]
        if 'error' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_error), V(result['error']))]
        if 'success' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_success), V(result['success']))]
        if 'failure' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_failure), V(result['failure']))]
        if 'filename' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_filename), V(result['filename']))]
        if 'ned-directory' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_ned_directory), V(result['ned-directory']))]
        if 'yang-directory' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_yang_directory), V(result['yang-directory']))]
        if 'missing' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_missing), V(result['missing']))]
        if 'enabled' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_enabled), V(result['enabled']))]
        if 'disabled' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_disabled), V(result['disabled']))]
        if 'marked' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_marked), V(result['marked']))]
        if 'get-config-reply' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_get_config_reply), V(result['get-config-reply']))]
        if 'get-reply' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_get_reply), V(result['get-reply']))]
        if 'hello-reply' in result:
            reply += [TV(XT(ns.ns.hash, ns.ns.pioneer_hello_reply), V(result['hello-reply']))]
            self.debug("action reply={0}".format(reply))

        dp.action_reply_values(uinfo, reply)
        return _ncs.CONFD_OK

    ######################################################################
    ##  REGISTRATION  ####################################################
    ######################################################################

    def __init__(self, debug, pipe):
        threading.Thread.__init__(self)
        self.debug = debug
        self.pipe = pipe

    def run(self):
        self.debug("Starting worker...")

        stop = False
        while not stop:
            self.init_daemon()

            _r = [self.csocket, self.wsocket, self.pipe]
            while True:
                (r, w, e) = select.select(_r, [], [])

                if self.pipe in r:
                    self.debug("Worker stop requested")
                    stop = True
                    break

                for s in r:
                    try:
                        dp.fd_ready(self.ctx, s)
                    except _ncs.error.EOF:
                        self.debug("EOF in worker/control socket, restarting")
                        break
                    except Exception as e:
                        self.debug("Exception in fd_ready: %s" % (str(e), ))

            self.stop_daemon()

        self.debug("Worker stopped")

    def cb_init(self, uinfo):
        dp.action_set_fd(uinfo, self.wsocket)

    def init_daemon(self):
        self.csocket = socket.socket()
        self.wsocket = socket.socket()
        self.msocket = socket.socket()

        self.ctx = dp.init_daemon("pioneer")

        dp.connect(
            dx=self.ctx,
            sock=self.csocket,
            type=dp.CONTROL_SOCKET,
            ip='127.0.0.1',
            port=_ncs.NCS_PORT
        )
        dp.connect(
            dx=self.ctx,
            sock=self.wsocket,
            type=dp.WORKER_SOCKET,
            ip='127.0.0.1',
            port=_ncs.NCS_PORT
        )
        maapi.connect(
            sock=self.msocket,
            ip='127.0.0.1',
            port=_ncs.NCS_PORT
        )

        dp.install_crypto_keys(self.ctx)
        dp.register_action_cbs(self.ctx, 'pioneer', self)
        dp.register_done(self.ctx)

    def stop_daemon(self):
        self.wsocket.close()
        self.csocket.close()
        dp.release_daemon(self.ctx)

# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------

class Action(object):

    def __init__(self, *args, **kwds):
        # Setup the NCS object, containing mechanisms
        # for communicating between NCS and this User code.
        self._ncs = NcsPyVM(*args, **kwds)

        # Just checking if the NCS logging works...
        self.debug('Initalizing object')

        # Register our 'finish' callback
        self._finish_cb = lambda: self.finish()
        self._ncs.reg_finish(self._finish_cb)
        self.mypipe = os.pipe()

        self.waithere = threading.Semaphore(0)  # Create as blocked

    # This method starts the user application in a thread
    def run(self):
        global _schemas_loaded

        self.debug("action.py:run starting")

        self.debug("run: starting action handler...")
        w = ActionHandler(self.debug, self.mypipe[0])

        # Since the ActionHandler object above is a thread, when we call the
        # start method the Thread class will invoke the
        # ActionHandler.run-method.
        w.start()
        self.debug("action.py:run: starting worker...")
        self._ncs.add_running_thread('Worker')

        # Wait here until 'finish' gets called
        self.debug("action.py:run: waiting for work...")
        self.waithere.acquire()

        # Inform the 'subscriber' that it has to shutdown
        os.write(self.mypipe[1], b'finish')
        w.join()

        self.debug("action.py:run: finished...")

    # Just a convenient logging function
    def debug(self, line):
        self._ncs.debug(line)

    # Callback that will be invoked by NCS when the system is shutdown.
    # Make sure to shutdown the User code, including any User created threads.
    def finish(self):
        self.waithere.release()

    ######################################################################
