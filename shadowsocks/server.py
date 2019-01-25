#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015 clowwindy
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

from __future__ import absolute_import, division, print_function, \
    with_statement

import sys
import os
import logging
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))
from shadowsocks import shell, daemon, eventloop, tcprelay, udprelay, \
    asyncdns, manager


def main():
    # 检查python版本
    shell.check_python()
   
    config = shell.get_config(False)    # 获取配置文件,其中参数False 是标识符is_local的假值,表示要获取非local配置

    daemon.daemon_exec(config)          # 检查配置是否要开启进程守护,仅在UNIX, Linux 上有效
    # 多用户分配设置处理
    if config['port_password']:
        if config['password']:
            logging.warning('warning: port_password should not be used with '
                         'server_port and password. server_port and password '
                         'will be ignored')
    else:
        config['port_password'] = {}
        server_port = config['server_port']
        if type(server_port) == list:
            for a_server_port in server_port:
                config['port_password'][a_server_port] = config['password']
        else:
            config['port_password'][str(server_port)] = config['password']

    if config.get('manager_address', 0):
        logging.info('entering manager mode')
        manager.run(config)
        return

    tcp_servers = []
    udp_servers = []
    dns_resolver = asyncdns.DNSResolver()   # 创建DNS查询对象
    port_password = config['port_password'] # 获取
    del config['port_password']             # 删除config 字典中的"port_password"键
    # 将多用户配置转换为单用户配置
    for port, password in port_password.items():
        a_config = config.copy()
        a_config['server_port'] = int(port) # 创建"server_port"键
        a_config['password'] = password # 创建"password"键
        logging.info("starting server at %s:%d" % (a_config['server'], int(port)))  # 记录服务开启
        tcp_servers.append(tcprelay.TCPRelay(a_config, dns_resolver, False))    # 添加TCP查询对象,TCP代理实现
        udp_servers.append(udprelay.UDPRelay(a_config, dns_resolver, False))    # 添加UDP查询对象

    # 开启服务
    def run_server():
        def child_handler(signum, _):
            logging.warning('received SIGQUIT, doing graceful shutting down..')
            list(map(lambda s: s.close(next_tick=True), tcp_servers + udp_servers))
        signal.signal(getattr(signal, 'SIGQUIT', signal.SIGTERM), child_handler)

        def int_handler(signum, _):
            sys.exit(1)
        signal.signal(signal.SIGINT, int_handler)

        try:
            loop = eventloop.EventLoop()    # 创建事件循环处理对象
            dns_resolver.add_to_loop(loop)  # 将DNS绑定到事件循环
            list(map(lambda s: s.add_to_loop(loop), tcp_servers + udp_servers))

            daemon.set_user(config.get('user', None))   # 开启角色进程守护
            
            loop.run()  # 开启事件处理死循环
            
        except Exception as e:
            shell.print_exception(e)    # 异常处理
            sys.exit(1) # 退出

    if int(config['workers']) > 1:
        if os.name == 'posix':
            children = []
            is_child = False
            for i in range(0, int(config['workers'])):
                r = os.fork()
                if r == 0:
                    logging.info('worker started')
                    is_child = True
                    run_server()
                    break
                else:
                    children.append(r)
            if not is_child:
                def handler(signum, _):
                    for pid in children:
                        try:
                            os.kill(pid, signum)
                            os.waitpid(pid, 0)
                        except OSError:  # child may already exited
                            pass
                    sys.exit()
                signal.signal(signal.SIGTERM, handler)
                signal.signal(signal.SIGQUIT, handler)
                signal.signal(signal.SIGINT, handler)

                # master
                for a_tcp_server in tcp_servers:
                    a_tcp_server.close()
                for a_udp_server in udp_servers:
                    a_udp_server.close()
                dns_resolver.close()

                for child in children:
                    os.waitpid(child, 0)
        else:
            logging.warn('worker is only available on Unix/Linux')
            run_server()
    else:
        run_server()


if __name__ == '__main__':
    main()
