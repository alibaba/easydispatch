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



def from_item_list_to_dict(item_str_list):
    item_dict = {}
    for item_str in item_str_list:
        item_list = parse_item_str(item_str)
        item_dict[item_list[0]] = float(item_list[1])
    return item_dict



def from_item_dict_to_list(item_dict): 
    return [f"{k}:{item_dict[k]}" for k in item_dict.keys()]


# https://stackoverflow.com/questions/4273466/reversible-hash-function
def hash_int(n):
    return ((0x0000FFFF & n)<<16) + ((0xFFFF0000 & n)>>16)
# hash(hash(429496729))