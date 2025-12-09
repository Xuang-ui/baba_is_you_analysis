import heapq
from collections import deque

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

def jaccard_similarity(a, b):
    interc, unionc = 0, 0
    if isinstance(a, str) and isinstance(b, str):
        a = [part.split(' ') for part in a.split('|')]
        b = [part.split(' ') for part in b.split('|')]
    for a_i, b_i in zip(a, b):
        interc += len(set(a_i) & set(b_i))
        unionc += len(set(a_i) | set(b_i))
    return interc / unionc if unionc > 0 else 1

def decoding(str):
    """
    数据统一为List[Dict]或者List[List]格式存储时的函数
    最外层用'|'分割，内层用','分割,键值对用':'分割
    """ 
    str = str.strip()
    if '|' in str:
        return [decoding(sub_str) for sub_str in str.split('|')]

    if ':' in str:
        pairs = str.split(';')
        return {decoding(pair.split(':')[0]): decoding(pair.split(':')[1]) for pair in pairs}
    
    if ',' in str:
        return tuple(decoding(part) for part in str.split(','))
    
    return int(str) if str.isdigit() else str

def encoding(data):
    """
    数据统一为List[Dict]或者List[List]格式存储时的函数
    最外层用'|'分割，内层用','分割,键值对用':'分割
    """ 
    if isinstance(data, list):
        return '|'.join([encoding(part) for part in data])
    
    if isinstance(data, dict):
        return ';'.join([f"{encoding(k)}:{encoding(v)}" for k, v in data.items() if v or v==0])
    
    if isinstance(data, tuple) or isinstance(data, list):
        return ','.join([encoding(part) for part in data])
    
    return str(data)

