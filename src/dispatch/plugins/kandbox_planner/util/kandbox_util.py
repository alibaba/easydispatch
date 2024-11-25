from dispatch.config import SEPERATOR_TOP_2, SEPERATOR_TOP_3
from datetime import datetime

def min_max_normalize(x, input_min, input_max):
    if input_max == input_min:
        return x
    y = (x - input_min) / (input_max - input_min)
    return y


def min_max_denormalize(y, input_min, input_max):
    x = (y * (input_max - input_min)) + input_min
    return x


def parse_item_str(item_str):
    item_list = item_str.split(":")
    if len(item_list) < 2:
        return item_list + [0]
    elif len(item_list) == 2:
        return [item_list[0], float(item_list[1])]
    else:
        raise ValueError(f"{item_str} is Not a proper item string, expecting item:0")

def parse_item_from_str(item_str, sep0, sep1,):
    accum_items = {}
    if len(item_str) < 3:
        return accum_items
    for s in item_str.split(sep0):
        if len(s) > 2:
            sp = s.split(sep1)
            accum_items[sp[0]] = int(sp[1])

    return accum_items

def from_item_list_to_dict(item_str_list):
    item_dict = {}
    for item_str in item_str_list:
        item_list = parse_item_str(item_str)
        item_dict[item_list[0]] = float(item_list[1])
    return item_dict

def from_time_window_str_to_list(tw_str):
    item_list = []
    if len(tw_str) < 1:
        return item_list
    item_str_list = tw_str.split(";")
    for item_str in item_str_list:
        if len(item_str) < 3:
            print(f"from_time_window_str_to_list: Wrong format: {item_str}")
        tw = item_str.split(",")
        item_list.append( (int(tw[0]), int(tw[1]))) 
    return item_list
# print(f"from_time_window_str_to_list: tested as : {from_time_window_str_to_list('1,2; 5,9')}")




def from_item_dict_to_list(item_dict): 
    return [f"{k}:{item_dict[k]}" for k in item_dict.keys()]


# https://stackoverflow.com/questions/4273466/reversible-hash-function
def hash_int(n):
    return ((0x0000FFFF & n)<<16) + ((0xFFFF0000 & n)>>16)
# hash(hash(429496729))


class GatheringListDict():
    def __init__(self):
        self.reset()
    def reset(self):
        self.value_list = [] 
        self.code2idx_dict = dict()
    def lookup_or_add(self, code, value = None):
        if code not in self.code2idx_dict:
            loc_i = len(self.value_list)
            self.code2idx_dict[code] = loc_i
            self.value_list.append(value)
        else:
            loc_i = self.code2idx_dict[code]
        return loc_i

    def append(self, code, value):
        loc_i = len(self.value_list)
        self.code2idx_dict[code] = loc_i
        self.value_list.append(value)
        return loc_i

def try_bytes_to_str(jobs_bstring):
    if type(jobs_bstring) == bytes:
        j_s = jobs_bstring.decode("utf-8")
    else:
        j_s = jobs_bstring
    return j_s


def get_area_code2slot_dict(slots = [], area_code_filter=set(), worker_code_filter=set()): 
    ac2w = {}
    ac2j = {}
    visited_slots = set()
    for si, s in enumerate(slots):
        if s.slot_code in visited_slots:
            print("repeated_slots in get_area_code2slot_dict")
            continue
        if len(area_code_filter) > 0:
            if s.area_code not in area_code_filter:
                continue
        if len(worker_code_filter) > 0:
            if s.worker_code not in worker_code_filter:
                continue
        visited_slots.add(s.slot_code)
        if s.area_code in ac2w:
            ac2w[s.area_code].append(s)
        else:
            ac2w[s.area_code] = [ s]
            ac2j[s.area_code] = []
    return ac2w, ac2j


# Usage:
# decode_solution(self.step_state.solution[0].tolist())

def decode_solution(solution, worker_length=4, print_before_return = True):
    worker_dict = {wi:[wi] for wi in range(worker_length)}
    eof = solution[-1]
    for wi in range(worker_length):
        idx = wi
        for _ in range(len(solution)):
            next = solution[idx]
            if idx == next:
                print(f"Error: idx == next at node {idx} of solution {solution}")
            if eof == next or idx == next:
                break
            worker_dict[wi].append(next)
            idx = next
        worker_dict[wi].append(f"E{len(solution)-1}")
    if print_before_return:
        for k,v in worker_dict.items():
            print(f"{k}-->{[j for j in v]}")

    return worker_dict
 
def encode_job_code2rustenv(job_code):
    ord_code = job_code
    job_seq = 0
    if job_code[-2:] == '-p':
        job_seq = 1
        ord_code = job_code[:-2] # .rstrip("-p")
    elif job_code[-2:] == '-d':
        job_seq = 2
        ord_code = job_code[:-2] # .rstrip("-d")
    return ord_code, job_seq

def encode_job_flex_form2rustenv(flex_form):
    form_list = [f"{k}{SEPERATOR_TOP_3}{v}" for k,v in flex_form.items() ]
    form_str = SEPERATOR_TOP_2.join(form_list)
    return form_str


def check_geo_range(geo_longitude, geo_latitude, team):
    longitude_max = team.geo_longitude + float(team.flex_form_data.get("longitude_diff_max", 1))
    longitude_min = team.geo_longitude - float(team.flex_form_data.get("longitude_diff_min", 1))
    latitude_max = team.geo_latitude + float(team.flex_form_data.get("latitude_diff_max", 1)) 
    latitude_min = team.geo_latitude - float(team.flex_form_data.get("latitude_diff_min", 1))

    check_geo_longitude = True if geo_longitude <= longitude_max and geo_longitude >= longitude_min else False
    check_geo_latitude = True if geo_latitude <= latitude_max and geo_latitude >= latitude_min else False
    return check_geo_longitude and check_geo_latitude

def slot_code2skill_code(slot_code):
    return f"_slot_:{slot_code}"    