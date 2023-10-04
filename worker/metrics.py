import time
import numpy as np
from config import Config


class MetricTypes:
    RECEIVED_MASSAGES = 0
    SENT_MESSAGES = 1
    LOCATION = 2
    SWARM_ID = 3
    LEASES = 4
    WAITS = 5
    ANCHOR = 6
    LOCALIZE = 7
    DROPPED_MESSAGES = 8
    FAILURES = 9
    GRANTED_LEASE = 10
    EXPIRED_LEASE = 11
    CANCELED_LEASE = 12
    RELEASED_LEASE = 13


def update_dict_sum(obj, key):
    if key in obj:
        obj[key] += 1
    else:
        obj[key] = 1


def log_msg_hist(hist, msg_type, label, cat):
    key_number = f'{cat}0_num_{label}_{msg_type.name}'
    key_num_cat = f'{cat}1_cat_num_{label}_{msg_type.get_cat()}'

    update_dict_sum(hist, key_number)
    update_dict_sum(hist, key_num_cat)


def get_messages_histogram(msgs, label, cat):
    hist = dict()

    for msg_hist in msgs:
        msg_type = msg_hist.value
        log_msg_hist(hist, msg_type, label, cat)

    return hist


class Metrics:
    def __init__(self, history, results_directory):
        self.results_directory = results_directory
        self.history = history
        self.general_metrics = {
            "B_bytes_sent": 0,
            "B_bytes_received": 0,
            "N_num_messages_sent": 0,
            "N_num_messages_received": 0,
            "N_num_dropped_send": 0,
            "N_num_dropped_receive": 0,
        }
        self.sent_msg_hist = {}
        self.received_msg_hist = {}
        self.network_timeline = []
        self.heuristic_timeline = []

    def log_sum(self, key, value):
        self.general_metrics[key] += value

    def log_max(self, key, value):
        self.general_metrics[key] = max(self.general_metrics[key], value)

    def log_min(self, key, value):
        self.general_metrics[key] = min(self.general_metrics[key], value)

    def log_received_msg(self, msg_type, length):
        if Config.TIMELINE_LOG:
            self.network_timeline.append([time.time(), 'r', length])
        log_msg_hist(self.received_msg_hist, msg_type, 'received', 'C')
        self.log_sum("N_num_messages_received", 1)
        self.log_sum("B_bytes_received", length)

    def log_sent_msg(self, msg_type, length):
        if Config.TIMELINE_LOG:
            self.network_timeline.append([time.time(), 's', length])
        log_msg_hist(self.sent_msg_hist, msg_type, 'sent', 'B')
        self.log_sum("N_num_messages_sent", 1)
        self.log_sum("B_bytes_sent", length)

    def log_heuristic_ran(self):
        if Config.TIMELINE_LOG:
            self.heuristic_timeline.append([time.time()])

    def get_total_distance(self):
        way_points = self.get_location_history()
        total_dist = 0
        for i in range(len(way_points) - 1):
            d = np.linalg.norm(way_points[i+1].value - way_points[i].value)
            total_dist += d

        return total_dist

    def get_total_bytes_sent(self):
        return sum([s.meta["length"] for s in self.get_sent_messages()])

    def get_total_bytes_received(self):
        return sum([s.meta["length"] for s in self.get_received_messages()])

    def get_sent_messages_histogram(self):
        return get_messages_histogram(self.get_sent_messages(), 'sent', 'B')

    def get_received_messages_histogram(self):
        return get_messages_histogram(self.get_received_messages(), 'received', 'C')

    def get_location_history(self):
        return self.history[MetricTypes.LOCATION]

    def get_received_messages(self):
        return self.history[MetricTypes.RECEIVED_MASSAGES]

    def get_sent_messages(self):
        return self.history[MetricTypes.SENT_MESSAGES]

    def get_granted_leases(self):
        return sum(self.history[MetricTypes.GRANTED_LEASE])

    def get_expired_leases(self):
        return sum(self.history[MetricTypes.EXPIRED_LEASE])

    def get_canceled_leases(self):
        return sum(self.history[MetricTypes.CANCELED_LEASE])

    def get_released_leases(self):
        return sum(self.history[MetricTypes.RELEASED_LEASE])

    def get_waits(self):
        return self.history[MetricTypes.WAITS]

    def get_dropped_messages(self):
        return sum(self.history[MetricTypes.DROPPED_MESSAGES])

    def get_failures(self):
        return self.history[MetricTypes.FAILURES]

    def get_final_report_(self):
        report = {}
        report.update(self.general_metrics)
        # report.update(self.sent_msg_hist)
        # report.update(self.received_msg_hist)
        return report

    def get_final_report(self):
        waits = [d.value for d in self.get_waits()]
        if Config.DURATION < 660:
            report = {
                "A0_total_distance": self.get_total_distance(),
                "A1_num_moved": len(waits),
                "A1_min_wait(s)": min(waits),
                "A1_max_wait(s)": max(waits),
                "A1_total_wait(s)": sum(waits),
                "A2_num_granted_leases": self.get_granted_leases(),
                "A2_num_expired_leases": self.get_expired_leases(),
                "A2_num_canceled_leases": self.get_canceled_leases(),
                "A2_num_released_leases": self.get_released_leases(),
                "A3_num_anchor": len(self.history[MetricTypes.ANCHOR]),
                "A3_num_localize": len(self.history[MetricTypes.LOCALIZE]),
                "A4_bytes_sent": sum([s.meta["length"] for s in self.get_sent_messages()]),
                "A4_bytes_received": sum([r.meta["length"] for r in self.get_received_messages()]),
                "A4_num_messages_sent": len(self.get_sent_messages()),
                "A4_num_messages_received": len(self.get_received_messages()),
                "A4_num_dropped_messages": self.get_dropped_messages(),
                "A5_num_failures": len(self.get_failures())
            }
            report.update(self.get_sent_messages_histogram())
            report.update(self.get_received_messages_histogram())
        else:
            report = {
                "A5_num_failures": len(self.get_failures())
            }

        return report
