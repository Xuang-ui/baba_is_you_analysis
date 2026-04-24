import heapq
from collections import deque
from typing import TYPE_CHECKING, Optional
import gc
import json
import pandas as pd
import pathlib
if TYPE_CHECKING:
    from mdpframework import Environment


ALL_MAP = ['intro', 'tutorial', 'base', 'target', 'maze', 'make', 'break', 'helper']
ACT_MARK = {'Up': '↑', 'Down': '↓', 'Left': '←', 'Right': '→', 'Undo': '↶', 'Restart': '↻'}
# ====== DataFrame with schema ======
def save_df_with_schema(df, csv_path):
    path = pathlib.Path(csv_path)
    # 1. 保存数据
    df.to_csv(path, index=False)
    # 2. 提取并保存类型映射 (将 dtype 转为字符串)
    schema = {col: str(dtype) for col, dtype in df.dtypes.items()}
    with open(path.with_suffix('.json'), 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=4)

def load_df_with_schema(csv_path):
    path = pathlib.Path(csv_path)
    if str(csv_path).endswith('.parquet'):
        return pd.read_parquet(path)
    json_path = path.with_suffix('.json')
    # 1. 读取类型字典
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            dtype_dict = json.load(f)
        # 2. 读取 CSV
        return pd.read_csv(path, dtype=dtype_dict)
    else:
        return pd.read_csv(path)

# ====== data structures ======

class Stack:
    "A container with a last-in-first-out (LIFO) queuing policy."
    def __init__(self):
        self.list = []

    def push(self,item):
        "Push 'item' onto the stack"
        self.list.append(item)

    def pop(self):
        "Pop the most recently pushed item from the stack"
        return self.list.pop()

    def isEmpty(self):
        "Returns true if the stack is empty"
        return len(self.list) == 0

class Queue:
    "A container with a first-in-first-out (FIFO) queuing policy."
    def __init__(self):
        self.list = []

    def push(self,item):
        "Enqueue the 'item' into the queue"
        self.list.insert(0,item)

    def pop(self):
        """
          Dequeue the earliest enqueued item still in the queue. This
          operation removes the item from the queue.
        """
        return self.list.pop()

    def isEmpty(self):
        "Returns true if the queue is empty"
        return len(self.list) == 0
    
class PriorityQueue:
    """
      Implements a priority queue data structure. Each inserted item
      has a priority associated with it and the client is usually interested
      in quick retrieval of the lowest-priority item in the queue. This
      data structure allows O(1) access to the lowest-priority item.
    """
    def  __init__(self):
        self.heap = []
        self.count = 0

    def push(self, item, priority):
        entry = (priority, self.count, item)
        heapq.heappush(self.heap, entry)
        self.count += 1

    def pop(self):
        (_, _, item) = heapq.heappop(self.heap)
        return item

    def isEmpty(self):
        return len(self.heap) == 0

    def update(self, item, priority):
        # If item already in priority queue with higher priority, update its priority and rebuild the heap.
        # If item already in priority queue with equal or lower priority, do nothing.
        # If item not in priority queue, do the same thing as self.push.
        for index, (p, c, i) in enumerate(self.heap):
            if i == item:
                if p <= priority:
                    break
                del self.heap[index]
                self.heap.append((priority, c, item))
                heapq.heapify(self.heap)
                break
        else:
            self.push(item, priority)

class Deque:
    def __init__(self):
        self.queue = deque()
    
    def push(self, item):
        self.queue.append(item)
    
    def pop(self):
        return self.queue.popleft()
    
    def isEmpty(self):
        return len(self.queue) == 0
    
    def __len__(self):
        return len(self.queue)
    
    def __repr__(self):
        return repr(self.queue)
    
    def __str__(self):
        return str(self.queue)

# ====== encoding/decoding ======

def decoding(string):
    """
    数据统一为List[Dict]或者List[List]格式存储时的函数
    最外层用'|'分割，内层用','分割,键值对用':'分割
    """ 
    string = string.strip()

    if string.startswith('['):
        if string == '[]':
            return []
        return [decoding(sub_str) for sub_str in string[1:-1].split('|')]

    if string.startswith('{'):
        if ':' not in string:
            return {}
        pairs = string[1:-1].split(';')
        return {decoding(pair.split(':')[0]): decoding(pair.split(':')[1]) for pair in pairs}
    
    if string.startswith('('):
        return tuple(decoding(part) for part in string[1:-1].split(','))
    
    if string.isdigit() or (string.startswith('-') and string[1:].isdigit()):
        return int(string)
    
    if '.' in string:
        try: 
            return float(string)
        except ValueError:
            return string
    
    return string

def encoding(data):
    """
    数据统一为List[Dict]或者List[List]格式存储时的函数
    最外层用'|'分割，内层用','分割,键值对用':'分割
    """ 
    if isinstance(data, list):
        return '[' + '|'.join([encoding(part) for part in data]) + ']'
    
    if isinstance(data, dict):
        return '{' + ';'.join([f"{encoding(k)}:{encoding(v)}" for k, v in data.items()]) + '}'
    
    if isinstance(data, tuple) or isinstance(data, set):
        return '(' + ','.join([encoding(part) for part in data]) + ')'
    
    return str(data)


# ====== calculation ======
def jaccard_similarity(a, b):

    a_rule = set([p+e for p, es in a.items() for e in es])
    b_rule = set([p+e for p, es in b.items() for e in es])
    intersection = len(a_rule & b_rule)
    union = len(a_rule | b_rule)
    return intersection / union if union != 0 else 0.0

# ====== data preparation ======
ALLMAP = ['intro', 'tutorial', 'base', 'target', 'maze', 'make', 'break', 'helper']
def get_plan_structure(env: 'Environment', map_name: Optional[str] = None) -> dict:
    if map_name is None or map_name not in ALLMAP:
        for map in ALLMAP:
            get_plan_structure(env, map)
        return
    from state_storage import get_data_manager
    from plan_hierachy import PlanBuilder
    dm = get_data_manager(f'recording/{map_name}')
    _, state_init = env.mm(map_name)
    pb = PlanBuilder(state_init)
    print(f'Start building plan structure for map {map_name}, to deal is {len(env.em(map_name))} subjects.')
    cumulated_subject = 0
    for uid, data in env.em(map_name).items():
        if uid >= 0:
            try:
                plan, states = pb.build_plan(data.Action)
                plan.create(int(uid))
                data['Grid'] = states
                data['Hierachy'] = plan.coding()
            except Exception as e:
                print(f"Error processing UID {uid} in map {map_name}: {e}")
                continue
            cumulated_subject += 1
        if cumulated_subject % 10 == 0:
            print(cumulated_subject, end=', ')
            gc.collect()

        if cumulated_subject % 100 == 0: 
            dm.save_all()

    dm.save_all()


if __name__ == "__main__":
    env = Environment(Gridmap)
    cols = ['Count', 'Action', 'Before', 'After', 'Hierachy', 'Grid',
        'pred_maximum','pred_weighted','pred_state_0','pred_state_1','pred_state_2','pred_state_3']
    env.init_experience('game_action_rt_with_hmm_pred.csv', cols)

    