#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2012-2015 clowwindy
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
# 本地客户端的实现方法

from __future__ import absolute_import, division, print_function, \
    with_statement

import sys
import os
import logging
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))
from shadowsocks import shell, daemon, eventloop, tcprelay, udprelay, asyncdns


def main():
    # 检查 python 版本
    shell.check_python()

    # fix py2exe
    if hasattr(sys, "frozen") and sys.frozen in \
            ("windows_exe", "console_exe"):
        p = os.path.dirname(os.path.abspath(sys.executable))
        os.chdir(p)

    config = shell.get_config(True) # 加载配置文件

    daemon.daemon_exec(config)  # 读取配置文件是否开启进程守护, 仅在UNIX ,Linux 上有效

    try:
        logging.info("starting local at %s:%d" %
                     (config['local_address'], config['local_port']))

        dns_resolver = asyncdns.DNSResolver()   # 创建dns 查询对象
        tcp_server = tcprelay.TCPRelay(config, dns_resolver, True)  # 创建 TCP 代理转发对象
        udp_server = udprelay.UDPRelay(config, dns_resolver, True)  # 创建 UDP 代理转发对象
        loop = eventloop.EventLoop()    # 创建事件处理对象
        # 将dns查询、tcp代理方式转发、udp代理方式转发绑定到事件循环
        dns_resolver.add_to_loop(loop)
        tcp_server.add_to_loop(loop)
        udp_server.add_to_loop(loop)

        def handler(signum, _):
            logging.warn('received SIGQUIT, doing graceful shutting down..')
            tcp_server.close(next_tick=True)
            udp_server.close(next_tick=True)
        signal.signal(getattr(signal, 'SIGQUIT', signal.SIGTERM), handler)  # "Ctrl + C" 中断指令

        def int_handler(signum, _):
            sys.exit(1)
        signal.signal(signal.SIGINT, int_handler)

        daemon.set_user(config.get('user', None))
        loop.run()  # 开启事件循环
    except Exception as e:
        shell.print_exception(e)
        sys.exit(1)

if __name__ == '__main__':
    main()
