import json
import os
import random
import time

import numpy as np
import threading
from message import Message, MessageTypes
from config import Config
from .types import StateTypes
from worker.network import PrioritizedItem
from itertools import combinations
from utils import write_json, dict_hash


class StateMachine:
    def __init__(self, context, sock, metrics, weight_policy, event_queue):
        self.state = None
        self.context = context
        self.metrics = metrics
        self.sock = sock
        self.event_queue = event_queue
        self.last_neighbors_hash = None
        self.eta = Config.ETA
        self.is_neighbors_processed = False
        self.solution_eta_idx = -1
        self.max_eta_idx = -1
        self.num_heuristic_invoked = 0
        self.last_expanded_time = 0
        self.last_h_ran_time = 0
        self.solution_range = 0
        self.sorted_neighbor_fids = []
        self.weight_policy = weight_policy

    def get_w(self):
        return self.context.w

    def get_c(self):
        return self.context.c

    def set_w(self, w):
        self.context.w = w

    def set_c(self, c):
        self.context.c = c

    def get_w_v(self, c):
        return self.weight_policy.compute(c, self.context.fid, self.context.el, self.context.neighbors)

    def is_proper_v(self, c):
        new_w = self.get_w_v(c)
        weights = [self.context.neighbors[i].w for i in c]
        return all([new_w >= w for w in weights])

    def attr_v(self, c):
        return self.get_w_v(c) if self.is_proper_v(c) else (-1,)

    def start(self):
        self.context.deploy()
        self.enter(StateTypes.SINGLE)

    def handle_discover(self, msg):
        pass

    def set_pair(self, c):
        w = self.get_w_v(c)
        # if w != self.get_w():
        self.set_c(c)
        self.set_w(w)
        self.context.set_pair()

    def handle_stop(self, msg):
        stop_msg = Message(MessageTypes.STOP).to_all()
        self.broadcast(stop_msg)
        self.cancel_timers()

        if not Config.DEBUG:
            min_fid = min(self.get_c() + (self.context.fid,))

            if len(self.get_c()):
                dists = []
                count = 0
                els = [self.context.el] + [self.context.neighbors[i].el for i in self.get_c()]
                for el_i, el_j in combinations(els, 2):
                    dists.append(np.linalg.norm(el_i - el_j))
                    count += 1
            else:
                dists = [0]
                count = 1
                els = [self.context.el]

            if Config.H == 2.1 or Config.H == 'canf':
                m_range = self.context.radio_range
                s_range = self.solution_range
            else:
                m_range = -1
                s_range = -1
            results = {
                # "5 weight": self.get_w()[0],
                "0 clique members": self.get_w()[1:],
                # "6 dist between each pair": dists,
                # "7 coordinates": [list(el) for el in els],
                "1 min dist": min(dists),
                "1 avg dist": sum(dists) / count,
                "1 max dist": max(dists),
                # "4 total dist": sum(dists),
                "2 max eta": self.max_eta_idx + 1,
                "2 solution eta": self.solution_eta_idx + 1,
                "3 max range": m_range,
                "3 solution range": s_range,
                "3 number of requested expansions": self.context.num_expansions,
                "3 number of neighbor driven expansions": self.context.num_neighbor_expansions,
                "4 h invoked": self.num_heuristic_invoked,
                "5 queue size": self.event_queue.qsize(),
            }
            results.update(self.metrics.get_final_report_())
            write_json(self.context.fid, results, self.metrics.results_directory, self.context.fid == min_fid)

            if Config.TIMELINE_LOG:
                with open(os.path.join(self.metrics.results_directory, f'nt_{self.context.fid}.n.json'), "w") as f:
                    json.dump(self.metrics.network_timeline, f)

                with open(os.path.join(self.metrics.results_directory, f'ht_{self.context.fid}.h.json'), "w") as f:
                    json.dump(self.metrics.heuristic_timeline, f)

        if Config.DEBUG:
            if len(self.get_c()):
                # self.context.set_pair(self.get_m().el)
                print(f"{self.context.fid} is paired with {self.get_c()} w={self.get_w()}"
                      f" num_heuristic_invoked={self.num_heuristic_invoked}")

            else:
                # self.context.set_pair(self.context.el)
                print(f"{self.context.fid} is single num_heuristic_invoked={self.num_heuristic_invoked}")
                # print(self.context.neighbors)

    def sort_neighbors(self):
        if Config.OPT_SORT:
            if len(self.context.neighbors) != len(self.sorted_neighbor_fids):
                self.sorted_neighbor_fids = sorted(self.context.neighbors.keys(),
                                                   key=lambda x: np.linalg.norm(
                                                       self.context.neighbors[x].gtl - self.context.gtl))
        else:
            self.sorted_neighbor_fids = sorted(self.context.neighbors.keys(),
                                               key=lambda x: np.linalg.norm(
                                                   self.context.neighbors[x].gtl - self.context.gtl))

    def expand_range(self):
        timestamp = time.time()
        if timestamp - self.last_expanded_time > Config.EXPANSION_TIMEOUT:
            self.context.double_range()
            self.last_expanded_time = timestamp

    def vns_shake(self, c, d):
        u = set(random.sample(c, d))
        n = list(set(self.context.neighbors.keys()) - set(c))
        if len(n) >= len(u):
            u_star = set(random.sample(n, len(u)))
            return tuple((set(c) - u) | u_star)
        return c

    def vns_local_search(self, c):
        for u in c:
            for u_star in list(set(self.context.neighbors.keys()) - set(c)):
                c_prime = tuple((set(c) - {u}) | {u_star})
                if self.attr_v(c_prime) > self.attr_v(c):
                    return c_prime
        return c

    def heuristic_vns(self, c_opt):
        if len(self.context.neighbors.keys()) < self.context.k - 1:
            return (), -1

        start_time = time.time()

        if not len(c_opt):
            c_opt = tuple(random.sample(self.context.neighbors.keys(), self.context.k - 1))

        while time.time() - start_time < Config.VNS_TIMEOUT:
            d = 1
            while d < self.context.k:
                c = self.vns_shake(c_opt, d)
                c_prime = self.vns_local_search(c)
                if self.attr_v(c_prime) > self.attr_v(c_opt):
                    c_opt = c_prime
                    d = 1
                else:
                    d += 1
        return c_opt, -1

    def heuristic_rs(self, c_cur):
        if len(self.context.neighbors.keys()) < self.eta:
            return (), -1
        c = c_cur
        subset = set(c_cur) | set(random.sample(self.context.neighbors.keys(), self.eta))
        for u in combinations(subset, self.context.k - 1):
            if self.attr_v(u) > self.attr_v(c):
                c = u
        return c, -1

    def heuristic_1(self, c):
        self.sort_neighbors()

        if len(self.sorted_neighbor_fids) < self.eta:
            return (), -1

        return tuple(random.sample(self.sorted_neighbor_fids[:self.eta], self.context.k - 1)), self.eta - 1

    # def heuristic_2(self, c):
    #     candidates = []
    #     last_idx = 0
    #
    #     # centrally sorted neighbor not used anymore
    #     for i in range(len(self.context.sorted_neighbors)):
    #         fid = self.context.sorted_neighbors[i]
    #         if fid in self.context.neighbors:
    #             c_n = self.context.neighbors[fid].c
    #             if len(c_n):
    #                 if self.context.fid in c_n:
    #                     candidates.append(fid)
    #                 else:
    #                     for n in c_n:
    #                         new_c = tuple(nc for nc in c_n if nc != n) + (fid,)
    #                         if all(nc in self.context.neighbors for nc in new_c):
    #                             if self.attr_v(new_c) > self.attr_v(c):
    #                                 candidates.append(fid)
    #                                 break
    #             else:
    #                 candidates.append(fid)
    #
    #         if len(candidates) == self.context.k - 1:
    #             last_idx = i
    #             break
    #
    #     if len(candidates) == self.context.k - 1:
    #         return tuple(candidates), last_idx
    #
    #     return (), last_idx

    def heuristic_2_1(self, c):
        candidates = []
        last_idx = 0

        if len(self.context.neighbors) < self.context.k - 1:
            self.expand_range()
            return (), last_idx

        self.sort_neighbors()

        for i, fid in enumerate(self.sorted_neighbor_fids):
            c_n = self.context.neighbors[fid].c
            if len(c_n):
                if self.context.fid in c_n:
                    candidates.append(fid)
                else:
                    for n in c_n:
                        new_c = tuple(nc for nc in c_n if nc != n) + (fid,)
                        if all(nc in self.context.neighbors for nc in new_c):
                            if self.attr_v(new_c) > self.attr_v(c):
                                candidates.append(fid)
                                break
            else:
                candidates.append(fid)

            if len(candidates) == self.context.k - 1:
                last_idx = i
                break

        if len(candidates) == self.context.k - 1:
            return tuple(candidates), last_idx

        self.expand_range()
        return (), last_idx

    def enter_single_state_with_heuristic(self):
        c = ()
        if self.is_proper_v(self.get_c()):
            c = self.get_c()

        n_hash = dict_hash(self.context.fid_to_w)
        # timestamp = time.time()
        if n_hash != self.last_neighbors_hash or random.random() < 0.2:
            self.last_neighbors_hash = n_hash
            # self.last_h_ran_time = timestamp

            for n in self.context.neighbors.values():
                if self.context.fid in n.c:
                    new_c = tuple(nc for nc in n.c if nc != self.context.fid) + (n.fid,)
                    if all(nc in self.context.neighbors for nc in new_c):
                        if self.attr_v(new_c) > self.attr_v(c):
                            c = new_c
            if Config.H == 'simpler':
                c_prime, last_idx = self.heuristic_1(c)
            elif Config.H == 2.1 or Config.H == 'canf':
                c_prime, last_idx = self.heuristic_2_1(c)
            elif Config.H == 'vns':
                c_prime, last_idx = self.heuristic_vns(c)
            elif Config.H == 'rs':
                c_prime, last_idx = self.heuristic_rs(c)
            self.num_heuristic_invoked += 1
            self.metrics.log_heuristic_ran()
            self.max_eta_idx = max(self.max_eta_idx, last_idx)
            if self.attr_v(c_prime) > self.attr_v(c):
                c = c_prime
                self.solution_eta_idx = last_idx
                self.solution_range = self.context.radio_range

            self.set_pair(c)

            discover_msg = Message(MessageTypes.DISCOVER).to_all()
            self.broadcast(discover_msg)

    def enter(self, state):
        self.state = state

        if self.state == StateTypes.SINGLE:
            self.enter_single_state_with_heuristic()
            self.put_state_in_q(MessageTypes.REENTER_SINGLE_STATE)

    def reenter(self, state):
        self.enter(state)

    def put_state_in_q(self, event):
        msg = Message(event).to_fls(self.context)
        item = PrioritizedItem(1, msg, False)
        self.event_queue.put(item)

    def drive(self, msg):
        event = msg.type
        self.context.update_neighbor(msg)

        if event == MessageTypes.DISCOVER:
            self.handle_discover(msg)
        elif event == MessageTypes.STOP:
            self.handle_stop(msg)
        elif event == MessageTypes.REENTER_SINGLE_STATE:
            if self.state == StateTypes.SINGLE:
                self.reenter(StateTypes.SINGLE)

    def broadcast(self, msg):
        msg.from_fls(self.context)
        length = self.sock.broadcast(msg)
        if length:
            self.context.log_sent_message(msg, length)
        else:
            self.context.log_dropped_send()

    # def send_to_server(self, msg):
    #     msg.from_fls(self.context).to_server()
    #     self.sock.send_to_server(msg)

    def start_timers(self):
        pass

    def cancel_timers(self):
        pass
