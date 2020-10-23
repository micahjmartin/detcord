"""
A thread management object
"""
import threading
from queue import Queue
from .actiongroup import ActionGroup
from paramiko.ssh_exception import SSHException

import __main__

THREAD_TIMEOUT = 1

class Threader(object):
    def __init__(self, connection_manager):
        self.threads = []
        self.queues = {}
        self.conman = connection_manager
        self.listener = {
            "q": None,
            "open": False
        }

    def run_action(self, action, host):
        """Given an action function and a host dict, run the action on the host
        """
        actiongroup = ActionGroup(
            host=host['ip'],
            user=host['user'],
            password=host['password'],
            port=host['port'],
            env=dict(__main__.env)
        )
        host = host['ip']
        host = host.lower().strip()
        if not self.listener.get("open"):
            self.listener['open'] = True
            self.listener['q'] = Queue()
            thread = threading.Thread(
                target=action_listener,
                args=(self.listener,)
            )
            self.threads.append(thread)
            thread.start()
        if host not in self.queues:
            # Create a queue for the host
            self.queues[host] = Queue()
            # make sure the host is in the connection manager
            self.conman.add_host(
                actiongroup.host,
                actiongroup.port,
                actiongroup.user,
                actiongroup.password
            )
            # Get an ssh connection for the thread to use
            try:
                try:
                    connection = self.conman.get_ssh_connection(host)
                except SSHException as E:
                    print("Bad stuff happened but we are trying to fix it!", E)
                    connection = self.conman.get_ssh_connection(host)
            except Exception as E:
                if not __main__.env.get('silent', False):
                    print("[{}] [-]: Cannot connect to host: {}".format(host, E))
                try:
                    __main__.on_detcord_action_fail(
                        host=host,
                        action=action.__name__,
                        exception=E
                    )
                except (AttributeError, TypeError) as _:
                    pass
                return False
            thread = threading.Thread(
                target=action_runner,
                args=(connection, self.queues[host], self.listener['q'])
            )
            self.threads.append(thread)
            thread.start()
        self.queues[host].put((action, actiongroup))
        #print("[{}] [+]: Connected to host".format(host))
        return True

    def close(self):
        self.conman.close()

def action_runner(connection, queue, output):
    while True:
        try:
            action, actiongroup = queue.get(timeout=THREAD_TIMEOUT)
        except:
            queue.task_done()
            return False
        try:
            actiongroup.connection = connection
            action(actiongroup)
        except Exception as E:
            output.put(str(E))
    return True

def action_listener(listener):
    queue = listener.get("q")
    while True:
        try:
            msg = queue.get(timeout=THREAD_TIMEOUT)
        except:
            listener['open'] = False
            #queue.task_done()
            queue = None
            return False
        if not __main__.env.get('silent', False):        
            print(msg)
    return True
